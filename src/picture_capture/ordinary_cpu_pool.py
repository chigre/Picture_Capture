"""Explicitly opt-in CPU-only multi-page ordinary drawing experiment.

No CUDA model may be started from this worker. The ordinary GUI default
remains the #492 one-worker-safe path. The CPU variant reuses the original
per-page Layout Core and PDIC writer, but must be validated for exact parity
against the GPU path before it can become a production default.
"""
from __future__ import annotations

import os
from typing import Any


_FLAG = "PICTURE_CAPTURE_ORDINARY_CPU_POOL"
_WORKERS = "PICTURE_CAPTURE_ORDINARY_CPU_WORKERS"
_THREADS = "PICTURE_CAPTURE_ORDINARY_CPU_THREADS"
_CHILD = "PICTURE_CAPTURE_ORDINARY_CPU_POOL_WORKER"


def cpu_pool_enabled(
    settings: Any, pages: int, *, flag: str | None = None,
) -> bool:
    if flag is None:
        flag = os.environ.get(_FLAG, "")
    # Illustration discovery can invoke other models: exclude until verified.
    return (
        str(flag).strip() == "1" and int(pages) >= 2
        and not bool(getattr(settings, "layout_mask_illustrations", False))
        and str(getattr(settings, "layout_transform", "identity")) == "identity"
    )


def cpu_pool_config(
    pages: int, *, cpus: int | None = None,
    requested_workers: str | None = None,
    requested_threads: str | None = None,
) -> tuple[int, int]:
    """Return (processes, inference threads per process).

    Auto uses 2 independent pages conservatively. Explicit worker counts
    can exceed six when hardware permits. Never allow worker*inference thread
    count to exceed available logical CPUs; reserve additional capacity for
    decoding/NumPy/OS work by using <=4 inference threads per process.
    """
    available = max(1, int(cpus if cpus is not None else os.cpu_count() or 1))
    if requested_workers is None:
        from .runtime_environment import runtime_setting
        requested_workers = (os.environ.get(_WORKERS)
                             or os.environ.get("PICTURE_CAPTURE_PADDLE_CPU_WORKERS")
                             or str(runtime_setting("paddle_cpu_workers", "auto")))
    if requested_threads is None:
        requested_threads = os.environ.get(_THREADS, "")
    try:
        selected = int(requested_workers)
    except (ValueError, TypeError):
        selected = 2
    count = max(1, min(int(pages), available, selected))
    auto_threads = max(1, min(4, available // count))
    try:
        per = int(requested_threads)
    except (TypeError, ValueError):
        per = auto_threads
    per = max(1, min(per, 4, max(1, available // count)))
    return count, per


def cpu_ordinary_page_job(
    image_path: str, settings: Any, pages: tuple[str, str, str],
    page_index: int, cpu_threads: int,
) -> int:
    """Entry to persistent Windows-spawned CPU page worker.

    Per-worker environment is set BEFORE the first PaddleOCR predictor is
    constructed. A separate strict constructor guard refuses to silently
    drop device="cpu" or cpu_threads on an incompatible PaddleOCR build.
    """
    per = max(1, min(8, int(cpu_threads)))
    os.environ[_CHILD] = "1"
    os.environ["PICTURE_CAPTURE_PADDLE_DEVICE"] = "cpu"
    # Advisory only: NumPy/Paddle imported during Windows spawn bootstrap may
    # have already initialized BLAS. cpu_threads is the authoritative control.
    os.environ["OMP_NUM_THREADS"] = str(per)
    from .runtime_environment import resolve_paddle_device

    resolve_paddle_device.cache_clear()
    if resolve_paddle_device() != "cpu":
        raise RuntimeError("CPU pool worker unexpectedly resolved a GPU device")
    from .processing import detect_entries_job
    return detect_entries_job(image_path, settings, pages, page_index)


__all__ = [
    "cpu_pool_enabled", "cpu_pool_config", "cpu_ordinary_page_job",
]
