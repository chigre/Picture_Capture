from __future__ import annotations

"""Keep the remaining Page/Layout runtime installation identical in workers.

``processing._understand_page_current`` calls ``_ensure_layout_runtime`` inside
ordinary-drawing workers. Long-band row recovery now lives statically in
``layout_physical_indent``. The worker-local helper still needs the same
column-drift runtime as GUI composition before Layout Core imports/calls the page
policy; otherwise drifting columns can produce false indentation entries.

This compatibility adapter extends the worker helper rather than duplicating the
Page Understanding algorithm. The explicit shared ``bootstrap.core`` profile
installs it for GUI, worker, CLI and other composed application consumers; bare
package import intentionally performs no runtime installation.
"""

from functools import wraps
from typing import Any


def install_spawn_layout_runtime(processing_module: Any) -> None:
    """Extend ``_ensure_layout_runtime`` to match GUI composition order."""
    if bool(getattr(processing_module, "_pc_spawn_layout_runtime_installed", False)):
        return

    original = processing_module._ensure_layout_runtime

    @wraps(original)
    def ensure_layout_runtime() -> None:
        # The historical helper installs, in order:
        #   robust_line_starts -> physical_indent
        original()

        # Long-band row recovery is static. Spawn workers still need the
        # same column-drift runtime as GUI before Layout Core calls page policy.
        from .layout_column_drift_runtime import install_layout_column_drift_runtime

        install_layout_column_drift_runtime()

    processing_module._ensure_layout_runtime = ensure_layout_runtime
    processing_module._pc_spawn_layout_runtime_installed = True


__all__ = ["install_spawn_layout_runtime"]
