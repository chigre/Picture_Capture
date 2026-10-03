from __future__ import annotations

"""Keep Page/Layout runtime installation identical in GUI and spawn workers.

``processing._understand_page_current`` calls ``_ensure_layout_runtime`` inside
ordinary-drawing workers.  The launcher installs four physical Layout runtimes
in this order, but historically the worker-local helper installed only the first
two.  On pages whose second column drifts slightly, that difference can turn
many body rows into false indentation entries even though the GUI Layout
diagnostic is correct.

This package-level adapter extends the worker helper rather than duplicating the
Page Understanding algorithm.  It is installed from ``picture_capture.__init__``
so fresh multiprocessing ``spawn`` interpreters receive the same runtime chain
without needing to execute the GUI launcher.
"""

from functools import wraps
from typing import Any


def install_spawn_layout_runtime(processing_module: Any) -> None:
    """Extend ``_ensure_layout_runtime`` to match the launcher runtime order."""
    if bool(getattr(processing_module, "_pc_spawn_layout_runtime_installed", False)):
        return

    original = processing_module._ensure_layout_runtime

    @wraps(original)
    def ensure_layout_runtime() -> None:
        # The historical helper installs, in order:
        #   robust_line_starts -> physical_indent
        original()

        # The GUI launcher then installs these two.  Spawn workers must do the
        # same before Layout Core imports/calls the page policy.
        from .layout_row_recovery_runtime import install_layout_row_recovery_runtime
        from .layout_column_drift_runtime import install_layout_column_drift_runtime

        install_layout_row_recovery_runtime()
        install_layout_column_drift_runtime()

    processing_module._ensure_layout_runtime = ensure_layout_runtime
    processing_module._pc_spawn_layout_runtime_installed = True


__all__ = ["install_spawn_layout_runtime"]
