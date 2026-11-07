from __future__ import annotations

"""Memory-conservative page-crop worker policy, independent of the GUI."""

import os
from collections.abc import Callable


def resolve_crop_worker_count(
    configured: int = 0,
    cpu_count: int | None = None,
    *,
    cpu_count_provider: Callable[[], int | None] = os.cpu_count,
) -> int:
    """Auto mode caps at four, explicit requests at eight and available CPUs."""
    cpus = max(1, int(cpu_count if cpu_count is not None else (cpu_count_provider() or 1)))
    try:
        requested = int(configured)
    except (TypeError, ValueError):
        requested = 0
    if requested > 0:
        return max(1, min(requested, cpus, 8))
    if cpus <= 2:
        return 1
    return min(4, max(2, cpus // 2))
