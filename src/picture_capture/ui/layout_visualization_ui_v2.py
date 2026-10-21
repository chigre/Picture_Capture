from __future__ import annotations

"""Robust installer for the main-window Layout visualization switch.

The first implementation searched the completed quick-settings widget tree for
``二、显示设置``.  That is unnecessarily fragile because collapsible sidebar
sections may add intermediary containers.  This installer captures the exact
LabelFrame at creation time and installs the display-only Layout toggle there.
"""

from typing import Any

from .layout_visualization_ui import (
    _install_display_toggle,
    draw_layout_visualization,
)


def install_layout_visualization(app_module: Any) -> None:
    """Install Layout visualization into the exact display-settings section."""
    cls = app_module.PictureCaptureApp
    if getattr(cls, "_layout_visualization_v2_installed", False):
        return

    original_section_frame = cls._section_frame
    original_build = cls._build_quick_settings
    original_redraw = cls.redraw

    def section_frame(
        self: Any,
        parent: Any,
        title: str,
        padding: int = 5,
        *,
        section_key: str | None = None,
    ) -> Any:
        frame = original_section_frame(
            self,
            parent,
            title,
            padding,
            section_key=section_key,
        )
        if str(title) == "二、显示设置" or str(section_key or "") == "aux":
            self._layout_visualization_display_section = frame
        return frame

    def build_quick_settings(self: Any, parent: Any) -> Any:
        result = original_build(self, parent)
        section = getattr(self, "_layout_visualization_display_section", None)
        if section is not None:
            # Pass the exact section itself.  _install_display_toggle normally
            # searches descendants, so temporarily expose a tiny wrapper whose
            # child list contains this frame directly.
            class _SectionRoot:
                def winfo_children(inner_self):
                    return [section]

            _install_display_toggle(self, _SectionRoot())
        else:
            # Compatibility fallback for unusual downstream UI replacements.
            _install_display_toggle(self, parent)
        return result

    def redraw(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original_redraw(self, *args, **kwargs)
        draw_layout_visualization(self)
        return result

    cls._section_frame = section_frame
    cls._build_quick_settings = build_quick_settings
    cls.redraw = redraw
    cls._layout_visualization_v2_installed = True
