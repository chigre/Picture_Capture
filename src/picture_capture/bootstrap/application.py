from __future__ import annotations

"""Stable application composition-root API."""

from typing import Any


def build_application() -> Any:
    """Return the fully prepared GUI application module.

    Importing this module remains lightweight; the GUI composition chain is
    imported only when an application is actually requested.
    """
    from .gui import prepare_gui_application

    return prepare_gui_application()


def main() -> int:
    """Run the prepared Picture Capture GUI."""
    return build_application().main()


__all__ = ["build_application", "main"]
