"""Explicit application bootstrap entrypoints.

The bootstrap package is the stable composition-root surface for Picture
Capture.  During the migration, the historical installer chain remains in
``picture_capture.launcher`` behind this API; subsequent refactor PRs move that
implementation here without changing the public startup path again.
"""

from .application import build_application, main

__all__ = ["build_application", "main"]
