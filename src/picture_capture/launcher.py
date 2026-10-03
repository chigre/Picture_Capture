from __future__ import annotations

"""Backward-compatible launcher facade.

Application composition now lives under :mod:`picture_capture.bootstrap`.
External callers that still import ``launcher.prepare_app_module`` or
``launcher.main`` keep the historical API while following the same composition
root as packaged entrypoints.
"""

from typing import Any


def prepare_app_module() -> Any:
    """Return the fully prepared GUI application module."""
    from .bootstrap.application import build_application

    return build_application()


def main() -> int:
    """Run Picture Capture through the explicit application bootstrap."""
    from .bootstrap.application import main as bootstrap_main

    return bootstrap_main()


__all__ = ["prepare_app_module", "main"]
