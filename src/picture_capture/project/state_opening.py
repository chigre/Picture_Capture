"""Real project-open and storage-recovery workflow for ProjectState.

The class and pickle identity remain in models.py. A call-time dependency map
preserves legacy monkeypatch hooks and avoids import cycles at module import.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def open_project_state(cls: type[Any], root: Path, *, deps: dict[str, Any]) -> Any:
    """Open a dictionary project without silently migrating legacy folders."""
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)

    images = deps["project_page_images"](root)

    # Storage v2: a clean/new scan folder gets exactly one software-owned
    # child directory. Existing legacy projects remain readable until the GUI
    # explicitly migrates them, so opening a project never silently moves data.
    # Do not create anything in an empty/non-project folder selected by mistake.
    from ..persistence.project_storage import (
        ensure_project_storage, has_legacy_project_data, is_managed_project,
        profile_path as active_profile_path,
        qt_root, settings_path as active_settings_path,
    )
    if images and (is_managed_project(root) or not has_legacy_project_data(root)):
        try:
            from .. import __version__
        except Exception:
            __version__ = "unknown"
        ensure_project_storage(root, __version__)
    # Recover page-level PNG/manifest transactions before any export can start.
    # An uncommitted transaction is rolled back; committed ones finish cleanup.
    from ..crop.publish import recover_incomplete_crop_publications
    recover_incomplete_crop_publications(root)
    json_settings = active_settings_path(root)
    if json_settings.exists():
        settings = deps["AppSettings"].from_json(json_settings)
    else:
        settings = deps["AppSettings"]()
        # A v3 profile sidecar can bootstrap a project that predates
        # settings.json.  Never apply this over an existing modern/legacy
        # settings file: those remain authoritative.
        try:
            from ..profile.dictionary import apply_project_profile_components
            apply_project_profile_components(active_profile_path(root), settings)
        except Exception:
            pass
    # settings.json is authoritative for mutable project state.  The profile
    # sidecar is only a compatibility fallback for projects that do not yet
    # have settings.json; it must never overwrite a user's newer selection.
    settings_has_profile = False
    if json_settings.exists():
        try:
            saved_settings = json.loads(json_settings.read_text(encoding="utf-8-sig"))
            settings_has_profile = bool(
                isinstance(saved_settings, dict)
                and str(saved_settings.get("dictionary_profile_id") or "").strip()
            )
        except (OSError, ValueError, TypeError):
            settings_has_profile = False
    if not settings_has_profile:
        try:
            from ..profile.dictionary import project_profile_preset_id
            settings.dictionary_profile_id = project_profile_preset_id(
                active_profile_path(root), getattr(settings, "dictionary_profile_id", "latin_structured_symbols")
            )
        except Exception:
            pass
    words_path = deps["resolve_wordslist_path"](root, settings.wordslist_path)
    words = deps["read_noncomment_lines"](words_path) if words_path.exists() else []
    active_qt = qt_root(root)
    (active_qt / "PaddleOCR").mkdir(parents=True, exist_ok=True)
    (active_qt / "PSW").mkdir(parents=True, exist_ok=True)
    (active_qt / "PWW").mkdir(parents=True, exist_ok=True)
    (active_qt / "PIC").mkdir(parents=True, exist_ok=True)
    (active_qt / "PicDic").mkdir(parents=True, exist_ok=True)
    return cls(root=root, images=images, settings=settings, words=words)
