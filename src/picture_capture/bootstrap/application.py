from __future__ import annotations

"""Stable application composition-root API.

Phase 1 introduces this module before moving the historical installer chain out
of :mod:`picture_capture.launcher`.  Keeping the public bootstrap stable first
lets packaged scripts, ``python -m`` and GUI smoke tests converge on one entry
path while the internal migration remains independently reviewable.
"""

from typing import Any


def build_application() -> Any:
    """Return the fully prepared GUI application module.

    The launcher call is deliberately lazy so importing ``picture_capture`` or
    this bootstrap package does not import Tk/application code by itself.
    ``launcher.prepare_app_module`` remains the compatibility implementation for
    this first migration step and will be moved behind this function next.
    """
    from ..launcher import prepare_app_module

    return prepare_app_module()


def main() -> int:
    """Run the prepared Picture Capture GUI."""
    return build_application().main()


__all__ = ["build_application", "main"]
