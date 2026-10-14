"""Bounded CPU parallelism for independent ordinary-drawing pages.

The existing spawn-safe detect_entries_job is still the sole producer of PDIC
and training baseline. This module only decides how many independent pages can
be processed at once. It does not change any Layout/OCR/role algorithm.
"""
from __future__ import annotations

import os


_ENV_VAR = "PICTURE_CAPTURE_ORDINARY_WORKERS"


def ordinary_draw_workers(
    page_count: int, *, cpu_count: int | None = None,
    override: str | None = None,
) -> int:
    """Choose a safe number of ordinary-drawing processes.

    Auto: 1 for a single page or <=2 CPUs; <=6 for larger machines.
    Optional environment override: 1..8 (also limited by CPU and page count).
    This is a process count, not a number of threads inside each worker.
    """
    count = max(0, int(page_count))
    if count <= 1:
        return 1
    cpus = max(1, int(cpu_count if cpu_count is not None else (os.cpu_count() or 1)))
    if override is None:
        override = os.environ.get(_ENV_VAR, "")
    try:
        configured = int(override) if override.strip() else 0
    except (TypeError, ValueError, AttributeError):
        configured = 0
    if configured > 0:
        return max(1, min(configured, cpus, count, 8))
    if cpus <= 2:
        return 1
    return max(1, min(count, cpus, 6, max(2, cpus // 3)))


__all__ = ["ordinary_draw_workers"]
