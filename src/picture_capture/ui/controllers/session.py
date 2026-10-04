from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...runtime_environment import legacy_user_config_files, user_config_root


SESSION_STATE_FILENAME = "session_state.json"


class SessionController:
    """Coordinate lightweight application-session persistence and restoration."""

    def __init__(self, app: Any) -> None:
        self.app = app

    @staticmethod
    def default_state_path() -> Path:
        return user_config_root() / SESSION_STATE_FILENAME

    def read_state(self) -> dict:
        app = self.app
        candidates = (
            app._session_path,
            *legacy_user_config_files(SESSION_STATE_FILENAME),
        )
        for candidate in candidates:
            try:
                if candidate.exists():
                    raw = json.loads(candidate.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        return raw
            except (OSError, ValueError, TypeError):
                continue
        return {}

    def save_state(self) -> None:
        app = self.app
        try:
            app._session_path.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "last_project": str(app.project.root) if app.project else "",
                "last_page": app.current_page.name if app.current_page else "",
                "last_page_index": app.current_index,
                "image_suffix": app.settings.image_suffix,
                "page_range": (
                    app.page_range_var.get()
                    if hasattr(app, "page_range_var")
                    else "current"
                ),
                "page_range_spec": (
                    app.page_range_spec_var.get()
                    if hasattr(app, "page_range_spec_var")
                    else ""
                ),
                "view_zoom_percent": round(app.view_scale * 100),
                "appearance_mode": app.appearance_preference,
                "section_expanded": dict(app.section_expanded),
            }
            tmp = app._session_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(app._session_path)
            app._last_session = state
        except OSError:
            # Session restoration is a convenience feature; never block editing
            # because a locked-down profile cannot persist it.
            pass

    def restore_last_session(self) -> None:
        app = self.app
        state = app._last_session or {}
        root_text = str(state.get("last_project") or "").strip()
        if not root_text:
            return
        root = Path(root_text).expanduser()
        if not root.is_dir():
            app.status_var.set(f"上次项目不可用：{root}")
            return
        if state.get("page_range") in {"current", "to_end", "specified"}:
            app.page_range_var.set(str(state.get("page_range")))
        app.page_range_spec_var.set(str(state.get("page_range_spec") or ""))
        try:
            zoom_value = state.get("view_zoom_percent")
            try:
                target_view_scale = (
                    min(3.0, max(0.08, float(zoom_value) / 100.0))
                    if zoom_value is not None
                    else None
                )
            except (TypeError, ValueError):
                target_view_scale = None
            app.status_var.set(f"正在后台恢复上次项目：{root}")
            app._load_project(
                root,
                requested_suffix=(
                    str(state.get("image_suffix") or "").strip() or None
                ),
                target_page=str(state.get("last_page") or "").strip() or None,
                target_index=state.get("last_page_index"),
                target_view_scale=target_view_scale,
            )
        except Exception as exc:
            app.status_var.set(f"无法恢复上次项目：{exc}")
