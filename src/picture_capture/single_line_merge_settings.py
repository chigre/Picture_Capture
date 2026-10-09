from __future__ import annotations

"""Per-page merge option for main-window single-line crop export.

The existing crop-settings surface persists to ``QT/_CropSettings.json`` rather
than the general project settings.  This module keeps the new option in that
same store and injects one checkbox into Settings Center -> crop settings without
changing the proofreading window's line-by-line crop behavior.
"""

from pathlib import Path
import json
import os
import tempfile
from typing import Any

from PIL import Image

from .crop.settings import SINGLE_LINE_MERGE_KEY
from .project_storage import crop_settings_path

CROP_SETTINGS_FILENAME = "_CropSettings.json"
MERGE_KEY = SINGLE_LINE_MERGE_KEY
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


def install_single_line_merge_settings_ui(app_module: Any) -> None:
    """Compatibility no-op; Settings crop ownership is static."""
    _ = app_module


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
