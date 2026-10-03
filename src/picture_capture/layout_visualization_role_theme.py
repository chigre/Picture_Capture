from __future__ import annotations

"""Small display-only theme overrides for Layout row-role diagnostics."""

from typing import Any, Callable


ENTRY_ROLE_COLOR = "#d32f2f"
BODY_ROLE_COLOR = "#1976d2"


def install_layout_role_theme() -> None:
    """Render entry rows red and keep body rows blue in Layout diagnostics."""
    from . import layout_visualization_summary as summary

    if getattr(summary, "_entry_role_red_theme_installed", False):
        return

    summary._ROLE_STYLE["entry"] = (ENTRY_ROLE_COLOR, "词条行")
    summary._ROLE_STYLE["headword"] = (ENTRY_ROLE_COLOR, "词条行")
    summary._ROLE_STYLE["body"] = (BODY_ROLE_COLOR, "正文行")
    summary._BODY_ROLE_STYLE = (BODY_ROLE_COLOR, "正文行")

    original: Callable[[Any, Any], str] = summary._format_summary

    def format_summary(app: Any, snapshot: Any) -> str:
        text = original(app, snapshot)
        return text.replace(
            "role strips: 绿色=词条行   蓝色=正文行",
            "role strips: 红色=词条行   蓝色=正文行",
        )

    summary._format_summary = format_summary
    summary._entry_role_red_theme_installed = True


__all__ = ["ENTRY_ROLE_COLOR", "BODY_ROLE_COLOR", "install_layout_role_theme"]
