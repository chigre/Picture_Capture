from __future__ import annotations

"""Persist the exact physical rows used by 【显示Layout】.

The cache key intentionally uses project-level settings, matching the settings
snapshot later passed to post-production export.  The cached geometry itself is
still the already-resolved per-page Layout result produced inside the wrapped
snapshot call.
"""

from pathlib import Path
from typing import Any

from .layout_rows_cache import capture_layout_rows


def install_layout_visualization_rows_cache() -> None:
    from . import layout_visualization_shared as shared

    if bool(getattr(shared, "_layout_visualization_rows_cache_installed", False)):
        return
    original = shared.shared_snapshot_for_app

    def wrapped(app: Any):
        project = getattr(app, "project", None)
        if project is None:
            return original(app)
        try:
            index = max(0, int(getattr(app, "current_index", 0)))
            images = list(getattr(project, "images", []) or [])
        except Exception:
            return original(app)
        if not (0 <= index < len(images)):
            return original(app)

        # Use the persisted/project settings as the cache identity.  The wrapped
        # Layout implementation is still free to derive page-effective settings
        # internally before producing the physical rows.
        settings = getattr(app, "settings", None)
        if settings is None:
            return original(app)
        with capture_layout_rows(
            Path(project.root),
            Path(images[index]),
            index,
            settings,
        ):
            return original(app)

    shared.shared_snapshot_for_app = wrapped
    shared._layout_visualization_rows_cache_installed = True


__all__ = ["install_layout_visualization_rows_cache"]
