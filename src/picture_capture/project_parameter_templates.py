"""Reusable project parameter snapshots for new volumes of a dictionary.

Only settings are copied. No PDIC/PPP, page-specific crop overrides,
OCR caches, review decisions, image files or per-page Profile measurements.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from tkinter import messagebox
from typing import Any

from .formats import write_text_atomic
from .models import AppSettings
from .project_storage import crop_settings_path, settings_path
from .runtime_environment import user_config_root


TEMPLATE_FILENAME = "new_project_parameters.json"
CROP_FILENAME = "_CropSettings.json"
TEMPLATE_FORMAT = "picture_capture_parameters"
TEMPLATE_VERSION = 1
IDENTITY_FIELDS = frozenset({
    "dictionary_full_name", "dictionary_abbreviation", "dictionary_isbn",
    "dictionary_body_page_range", "image_suffix", "page_bookmarks",
    "wordslist_path",
})


def default_template_path() -> Path:
    return user_config_root() / TEMPLATE_FILENAME


def _crop_parameters(project_root: Path | None) -> dict[str, Any]:
    if project_root is None:
        return {}
    path = crop_settings_path(project_root, CROP_FILENAME)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    # Page-specific crop overrides belong to the source volume.
    return {key: value for key, value in loaded.items()
            if key not in {"special_pages", "page_overrides"}}


def capture_parameters(
    settings: AppSettings, project_root: Path | None = None,
) -> dict[str, Any]:
    values = asdict(settings)
    return {
        "format": TEMPLATE_FORMAT,
        "version": TEMPLATE_VERSION,
        "settings": {key: value for key, value in values.items()
                     if key not in IDENTITY_FIELDS},
        "crop_settings": _crop_parameters(project_root),
    }


def save_default_parameters(
    settings: AppSettings, project_root: Path | None = None,
    *, path: Path | None = None,
) -> Path:
    destination = default_template_path() if path is None else Path(path)
    snapshot = capture_parameters(settings, project_root)
    write_text_atomic(
        destination, json.dumps(snapshot, ensure_ascii=False, indent=2) + chr(10),
    )
    return destination


def _read_snapshot(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(loaded, dict)
        or loaded.get("format") != TEMPLATE_FORMAT
        or loaded.get("version") != TEMPLATE_VERSION
        or not isinstance(loaded.get("settings"), dict)
        or not isinstance(loaded.get("crop_settings"), dict)
    ):
        raise ValueError("参数模板格式不正确")
    return loaded


def load_parameters(
    source_project: Path | None = None,
    *,
    default_path: Path | None = None,
) -> dict[str, Any] | None:
    if source_project is None:
        return _read_snapshot(default_template_path() if default_path is None else default_path)
    settings_file = settings_path(Path(source_project))
    if not settings_file.is_file():
        raise FileNotFoundError(f"现有项目没有已保存的参数：{settings_file}")
    return capture_parameters(
        AppSettings.from_json(settings_file), Path(source_project),
    )


def apply_parameters_to_project(
    project: Any,
    source_project: Path | None = None,
    *,
    default_path: Path | None = None,
) -> bool:
    """Apply a source volume or user's saved defaults to a *new* project only."""
    snapshot = load_parameters(source_project, default_path=default_path)
    if snapshot is None:
        return False
    values = snapshot["settings"]
    for name, value in values.items():
        if name in AppSettings.__dataclass_fields__ and name not in IDENTITY_FIELDS:
            setattr(project.settings, name, value)
    project.settings.to_json(settings_path(project.root))
    crop = snapshot["crop_settings"]
    if crop:
        file = crop_settings_path(project.root, CROP_FILENAME)
        # Never propagate old page-specific fields or overwrite existing
        # saved new-volume overrides.
        original: dict[str, Any] = {}
        if file.exists():
            try:
                current = json.loads(file.read_text(encoding="utf-8"))
                if isinstance(current, dict):
                    original = current
            except (OSError, ValueError, TypeError):
                pass
        original.update(crop)
        write_text_atomic(
            file, json.dumps(original, ensure_ascii=False, indent=2) + chr(10),
        )
    return True


def save_dialog_parameters_as_default(dialog: Any) -> None:
    """Settings Center action: validate and capture the current parameters."""
    if not dialog.save(close=False):
        return
    app = dialog.parent
    root = getattr(getattr(app, "project", None), "root", None)
    try:
        save_default_parameters(app.settings, root)
    except (OSError, ValueError, TypeError) as exc:
        messagebox.showerror("保存默认参数失败", str(exc), parent=dialog)
        return
    messagebox.showinfo(
        "默认参数已保存",
        "以后新建项目将自动使用这些布局、OCR、切图等参数。"
        "词典名称、图片格式、当前页书签和旧卷逐页数据不会复制。",
        parent=dialog,
    )
