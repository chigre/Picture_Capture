from __future__ import annotations

"""Keep the remaining Page/Layout runtime preparation identical in workers.

``processing._understand_page_current`` calls ``_ensure_layout_runtime`` inside
ordinary-drawing workers. Long-band row recovery and column-drift indent
remeasurement are now static. The helper still prepares robust line starts and
physical-indent behavior through the historical processing entry point.

This compatibility adapter remains a separate spawn-runtime seam so its final
retirement can be proven independently rather than bundled into Phase 5S.
"""

from functools import wraps
from typing import Any


def install_spawn_layout_runtime(processing_module: Any) -> None:
    """Retain the idempotent worker entry wrapper without column-drift patching."""
    if bool(getattr(processing_module, "_pc_spawn_layout_runtime_installed", False)):
        return

    original = processing_module._ensure_layout_runtime

    @wraps(original)
    def ensure_layout_runtime() -> None:
        original()

    processing_module._ensure_layout_runtime = ensure_layout_runtime
    processing_module._pc_spawn_layout_runtime_installed = True


__all__ = ["install_spawn_layout_runtime"]
