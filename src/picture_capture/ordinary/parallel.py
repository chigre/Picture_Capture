"""Emergency safe serialization of ordinary page detection.

Normal drawing calls GPU-capable PaddleOCR TextDetection as part of shared
Layout geometry, even though ordinary drawing performs no OCR recognition.
Each spawned process loads its own model and keeps private full-page NumPy
buffers, so CPU-core count is NOT a safe worker-count proxy. Until a dedicated
single-GPU inference service plus memory-aware CPU-only page execution has
been measured and accepted, ordinary batches MUST stay one-process-only.

This guard intentionally ignores the legacy PICTURE_CAPTURE_ORDINARY_WORKERS
override (including 6 and 8 persisted via setx). Keeping the public function
signature permits a later measured design to use a revised policy without
changing unrelated GUI call sites.
"""
from __future__ import annotations


def ordinary_draw_workers(
    page_count: int, *, cpu_count: int | None = None,
    override: str | None = None,
) -> int:
    """Require one reusable worker for every ordinary drawing batch.

    A zero-page request still returns 1: the caller handles empty selections.
    Former multi-worker overrides are intentionally disabled for safety.
    """
    return 1


__all__ = ["ordinary_draw_workers"]
