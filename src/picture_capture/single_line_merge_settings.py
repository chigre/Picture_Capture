from __future__ import annotations

"""Per-page merge option for main-window single-line crop export.

The existing crop-settings surface persists to ``QT/_CropSettings.json`` rather
than the general project settings.  This module keeps the new option in that
same store and injects one checkbox into Settings Center -> crop settings without
changing the proofreading window's line-by-line crop behavior.
"""

from functools import wraps
from pathlib import Path
import json
import os
import tempfile
from typing import Any, Iterable
import tkinter as tk
from tkinter import ttk

from PIL import Image

from .project_storage import crop_settings_path

CROP_SETTINGS_FILENAME = "_CropSettings.json"
MERGE_KEY = "single_line_crop_merge_by_page"
MERGE_LABEL = "单行切图按页合并"
# Scanned/JPEG paper that is visually white often contains tiny 251–254 level
# compression variations. Treat those as white background while preserving
# ordinary gray/black printed strokes.
WHITE_TRIM_THRESHOLD = 250
MERGE_HELP = (
    "开启后，主界面【单行切图】仍按校对界面的同一裁切规则逐行取图。"
    "合并前会先对每个小切片进行四周白边裁切，完全空白的切片直接丢弃；"
    "剩余有效切片再按阅读顺序纵向合成为一张 PNG，每页只保留一张合并图。"
    "关闭时保持一行一张小图。此选项不改变校对窗口内部的逐行显示。"
)


def _settings_path(project_root: Path) -> Path:
    return crop_settings_path(Path(project_root), CROP_SETTINGS_FILENAME)


def load_merge_by_page(project_root: Path) -> bool:
    path = _settings_path(project_root)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    if not isinstance(payload, dict):
        return False
    return bool(payload.get(MERGE_KEY, False))


def save_merge_by_page(project_root: Path, enabled: bool) -> Path:
    """Update only the merge flag while preserving every existing crop option."""
    path = _settings_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = dict(loaded)
        except (OSError, ValueError, TypeError):
            payload = {}
    payload[MERGE_KEY] = bool(enabled)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return path


def _trim_white_border(
    image: Image.Image,
    *,
    threshold: int = WHITE_TRIM_THRESHOLD,
) -> Image.Image | None:
    """Return content-tight RGB crop, or ``None`` for an all-white slice.

    The threshold intentionally treats only near-white paper as background.
    Geometry of the original line crop is not recomputed; this is a pure output
    compaction step used only after ``split_single_lines`` has finished.
    """
    rgb = image.convert("RGB")
    gray = rgb.convert("L")
    mask = gray.point(lambda value: 255 if int(value) < int(threshold) else 0)
    try:
        bbox = mask.getbbox()
    finally:
        mask.close()
        gray.close()
    if bbox is None:
        rgb.close()
        return None
    if bbox == (0, 0, rgb.width, rgb.height):
        return rgb
    trimmed = rgb.crop(bbox)
    rgb.close()
    return trimmed


def _write_manifest_atomic(path: Path, text: str) -> None:
    temp = path.with_name(f".{path.name}.tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def merge_page_line_images(
    image_path: Path,
    records: list[Any],
    output_dir: Path,
) -> Path | None:
    """Trim and stack one page's generated line crops into one lossless PNG.

    ``records`` come directly from the mature ``split_single_lines`` path, so
    crop geometry is never recalculated here. Each generated line image first
    loses its near-white outer border; fully white slices are discarded. The
    remaining content-tight slices are then composed in record/read order.
    """
    if not records:
        return None

    output_dir = Path(output_dir)
    source_paths = [output_dir / str(record.filename) for record in records]
    existing = [path for path in source_paths if path.is_file()]
    if not existing:
        return None

    page_stem = Path(image_path).stem
    merged_name = f"{page_stem}_SW_PAGE.png"
    merged_path = output_dir / merged_name
    manifest_path = output_dir / f"{page_stem}.PSWords"

    images: list[Image.Image] = []
    merged: Image.Image | None = None
    try:
        for path in existing:
            with Image.open(path) as opened:
                trimmed = _trim_white_border(opened)
            if trimmed is not None:
                images.append(trimmed)

        # A page can legitimately contain only false/empty line slices. Do not
        # manufacture a useless white page image in that case.
        if not images:
            _write_manifest_atomic(manifest_path, "")
            merged_path.unlink(missing_ok=True)
            for path in existing:
                path.unlink(missing_ok=True)
            return None

        width = max(image.width for image in images)
        height = sum(image.height for image in images)
        merged = Image.new("RGB", (max(1, width), max(1, height)), "white")
        y = 0
        for image in images:
            merged.paste(image, (0, y))
            y += image.height

        merged_temp = output_dir / f".{merged_name}.tmp"
        manifest_temp = output_dir / f".{manifest_path.name}.tmp"
        try:
            merged.save(merged_temp, format="PNG")
            manifest_temp.write_text(merged_name + "\n", encoding="utf-8")
            os.replace(merged_temp, merged_path)
            os.replace(manifest_temp, manifest_path)
        except Exception:
            merged_temp.unlink(missing_ok=True)
            manifest_temp.unlink(missing_ok=True)
            raise

        # Delete source slices only after the merged image and manifest have
        # both been published successfully. Blank slices are removed here too.
        for path in existing:
            if path != merged_path:
                path.unlink(missing_ok=True)
        return merged_path
    finally:
        if merged is not None:
            merged.close()
        for image in images:
            image.close()


def _walk_widgets(root: tk.Misc) -> Iterable[tk.Misc]:
    for child in root.winfo_children():
        yield child
        yield from _walk_widgets(child)


def _widget_text(widget: tk.Misc) -> str:
    try:
        return str(widget.cget("text") or "")
    except (tk.TclError, AttributeError):
        return ""


def _find_crop_tab(dialog: Any) -> tk.Misc | None:
    for widget in _walk_widgets(dialog):
        if not isinstance(widget, ttk.Notebook):
            continue
        try:
            for tab_id in widget.tabs():
                text = str(widget.tab(tab_id, "text") or "")
                if "切图" in text:
                    return dialog.nametowidget(tab_id)
        except tk.TclError:
            continue
    return None


def _find_crop_group(tab: tk.Misc) -> tk.Misc:
    label_frames: list[tk.Misc] = []
    for widget in _walk_widgets(tab):
        if isinstance(widget, ttk.LabelFrame):
            label_frames.append(widget)
    for wanted in ("通用切图规则", "单行切图", "批量切图"):
        for frame in label_frames:
            if wanted in _widget_text(frame):
                return frame
    return label_frames[0] if label_frames else tab


def _next_grid_row(parent: tk.Misc) -> int:
    rows: list[int] = []
    for child in parent.winfo_children():
        try:
            info = child.grid_info()
            if info:
                rows.append(int(info.get("row", 0)))
        except (tk.TclError, TypeError, ValueError):
            pass
    return max(rows, default=-1) + 1


def _project_root(dialog: Any) -> Path | None:
    project = getattr(getattr(dialog, "parent", None), "project", None)
    root = getattr(project, "root", None)
    return Path(root) if root is not None else None


def _persist_dialog_value(dialog: Any) -> None:
    root = _project_root(dialog)
    variable = getattr(dialog, "single_line_crop_merge_by_page_var", None)
    if root is None or variable is None:
        return
    try:
        enabled = bool(variable.get())
    except Exception:
        return
    save_merge_by_page(root, enabled)


def _install_checkbox(dialog: Any) -> None:
    if getattr(dialog, "_pc_single_line_merge_checkbox", None) is not None:
        return
    root = _project_root(dialog)
    tab = _find_crop_tab(dialog)
    if root is None or tab is None:
        return
    group = _find_crop_group(tab)
    variable = tk.BooleanVar(value=load_merge_by_page(root))
    dialog.single_line_crop_merge_by_page_var = variable

    check = ttk.Checkbutton(
        group,
        text=MERGE_LABEL,
        variable=variable,
        # Settings Center is auto-save. Persist immediately on the same user
        # gesture instead of inventing a separate save/close lifecycle.
        command=lambda: _persist_dialog_value(dialog),
    )
    manager = ""
    try:
        children = group.winfo_children()
        manager = next(
            (str(child.winfo_manager() or "") for child in children if child.winfo_manager()),
            "",
        )
    except tk.TclError:
        manager = ""
    try:
        if manager == "grid":
            row = _next_grid_row(group)
            check.grid(row=row, column=0, columnspan=2, sticky="w", pady=4)
            info = ttk.Label(group, text="ⓘ", foreground="#6b7280", cursor="hand2")
            info.grid(row=row, column=2, sticky="w", padx=(8, 0))
        else:
            check.pack(anchor="w", pady=4)
            info = None
    except tk.TclError:
        check.destroy()
        return

    def show_help(_event=None) -> None:
        try:
            dialog._show_check_help(MERGE_KEY)
            return
        except Exception:
            pass
        try:
            dialog.help_title_var.set(MERGE_LABEL)
            dialog.help_body_var.set(MERGE_HELP)
        except Exception:
            pass

    for widget in (check, info):
        if widget is None:
            continue
        try:
            widget.bind("<Enter>", show_help, add="+")
            widget.bind("<FocusIn>", show_help, add="+")
            widget.bind("<Button-1>", show_help, add="+")
        except tk.TclError:
            pass
    dialog._pc_single_line_merge_checkbox = check


def install_single_line_merge_settings_ui(app_module: Any) -> None:
    """Add the merge checkbox to Settings Center -> crop settings."""
    dialog = app_module.SettingsDialog
    if bool(getattr(dialog, "_pc_single_line_merge_settings_installed", False)):
        return

    # Make the standard right-side help resolver aware of the option when the
    # current SettingsDialog exposes the shared help dictionaries.
    if hasattr(dialog, "CHECK_HELP"):
        dialog.CHECK_HELP = dict(dialog.CHECK_HELP)
        dialog.CHECK_HELP[MERGE_KEY] = MERGE_HELP

    # The integrated crop page rewrites _CropSettings.json whenever another crop
    # control auto-saves. Re-append this optional key after that writer so it can
    # never be dropped by the older fixed-schema payload.
    for method_name in (
        "_save_integrated_crop_settings",
        "save", "_save", "apply", "_apply", "save_settings", "_save_settings",
        "apply_settings", "_apply_settings", "save_and_close", "_save_and_close",
    ):
        original = getattr(dialog, method_name, None)
        if not callable(original) or bool(getattr(original, "_pc_merge_wrapped", False)):
            continue

        @wraps(original)
        def wrapped(self, *args, __original=original, **kwargs):
            result = __original(self, *args, **kwargs)
            _persist_dialog_value(self)
            return result

        wrapped._pc_merge_wrapped = True  # type: ignore[attr-defined]
        setattr(dialog, method_name, wrapped)

    original_init = dialog.__init__

    @wraps(original_init)
    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _install_checkbox(self)

    dialog.__init__ = wrapped_init
    dialog._pc_single_line_merge_settings_installed = True


__all__ = [
    "MERGE_KEY",
    "MERGE_LABEL",
    "WHITE_TRIM_THRESHOLD",
    "_trim_white_border",
    "load_merge_by_page",
    "merge_page_line_images",
    "save_merge_by_page",
    "install_single_line_merge_settings_ui",
]
