"""Shared persistence for compact Project Profile controls.

Both the wizard and the compact menus edit AppSettings and its canonical
v3 Project Profile; there must not be a second set of OCR settings.
"""
from __future__ import annotations

from typing import Any

from ..dictionary_profile import write_project_profile
from ..project_storage import profile_path


def profile_changes_allowed(app: Any) -> bool:
    if getattr(app, "_batch_active", False):
        app.status_var.set("批量任务进行中，不能修改 Project Profile 参数")
        return False
    return True


def persist_profile_changes(app: Any) -> None:
    """Save the existing settings and Profile format without changing versions."""
    settings = app.settings
    settings.profile_last_validated_pages = []
    project = getattr(app, "project", None)
    if project is not None:
        app.save_settings()
        write_project_profile(
            profile_path(project.root), settings,
            settings.dictionary_profile_id, force=True,
        )
    app.sync_quick_settings()
    app.redraw()
