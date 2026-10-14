"""Experimental ordinary drawing: one GPU layout producer, bounded CPU consumers.

This module is deliberately opt-in. It constructs the SAME per-page prepared
analysis image and SAME detector settings as ordinary Layout Core, but performs
Paddle TextDetection only in one persistent GPU producer process. Its small,
pickleable LayoutEstimate is transferred to a separate CPU worker which runs
the unchanged final ordinary detection and PDIC/automatic-baseline writer.

No GPU model or full-resolution pixel array is ever serialized to the CPU
worker. A missing/mismatched/unused GPU estimate is a fatal page error; it must
never silently fall back to a second Paddle detector or a changed VB output.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from dataclasses import replace
import os
from pathlib import Path
from typing import Any, Iterator

from PIL import Image


_ENV = "PICTURE_CAPTURE_ORDINARY_GPU_PIPELINE"


def staged_pipeline_enabled(
    settings: Any, count: int, *, flag: str | None = None,
) -> bool:
    """Never auto-enable after the six-GPU-model resource exhaustion report.

    Only the real auto-layout Paddle-bound path, with illustration masking
    disabled, is currently supported. Other configurations retain serial
    detection until their exact preflight parity is verified.
    """
    if flag is None:
        flag = os.environ.get(_ENV, "")
    return (
        str(flag).strip() == "1"
        and int(count) >= 2
        and bool(getattr(settings, "ordinary_auto_layout", False))
        and not bool(getattr(settings, "layout_mask_illustrations", False))
        and str(getattr(settings, "layout_transform", "identity")) == "identity"
    )


@dataclass(frozen=True)
class PreparedLayoutEstimate:
    """Immutable, small per-page preflight fact, not a model or image tensor."""

    value: Any
    page_size: tuple[int, int]
    source_size_bytes: int
    source_mtime_ns: int
    detector_settings_repr: str
    page_index: int


@dataclass
class _Consumption:
    prepared: PreparedLayoutEstimate
    consumed: int = 0
    invalid: bool = False


_ACTIVE: ContextVar[_Consumption | None] = ContextVar(
    "picture_capture_gpu_prepared_layout", default=None,
)


@contextmanager
def use_prepared_layout(
    prepared: PreparedLayoutEstimate,
) -> Iterator[_Consumption]:
    """Install a one-use estimate for the current CPU worker task only."""
    state = _Consumption(prepared)
    token = _ACTIVE.set(state)
    try:
        yield state
    finally:
        _ACTIVE.reset(token)


def take_prepared_layout(image: Image.Image, settings: Any) -> Any | None:
    """Use exactly one injected estimate or run the legacy detector if absent.

    Called ONLY by the policy's authoritative detector entrypoint. A mismatch
    must fail closed; never invoke a second Paddle model in the CPU stage.
    """
    state = _ACTIVE.get()
    if state is None:
        return None
    expected = state.prepared
    if (
        state.consumed != 0
        or tuple(image.size) != expected.page_size
        or repr(settings) != expected.detector_settings_repr
    ):
        state.invalid = True
        raise RuntimeError("GPU Layout preflight mismatch/repeated detector call")
    state.consumed += 1
    return expected.value


def reject_cpu_worker_detector() -> None:
    """Reject unexpected Paddle TextDetection inside a staged CPU page job.

    Processing has a legacy broad fallback from Layout failure to VB. Mark the
    current preflight invalid BEFORE raising so that this cannot silently
    publish a different PDIC with plausible marker counts.
    """
    state = _ACTIVE.get()
    if state is not None:
        state.invalid = True
        raise RuntimeError("CPU worker attempted another Paddle GPU Layout detector")


def validate_prepared_layout(state: _Consumption) -> None:
    if state.invalid or state.consumed != 1:
        raise RuntimeError(
            "GPU Layout preflight not consumed exactly once; refuse PDIC write"
        )


def prepare_gpu_layout_job(
    image_path: str, settings: Any, page_index: int,
) -> PreparedLayoutEstimate:
    """One GPU model-owning process; no PDIC, baseline or settings writes."""
    from .image_utils import build_analysis_image, normalize_page_rgb
    from .profile_semantics import effective_page_settings
    from .layout_detection import detect_layout_parameters

    from time import perf_counter
    from .draw_performance_profile import enabled as profile_enabled, record_page
    profiling = profile_enabled()
    tick = perf_counter()
    stages = {}
    source_path = Path(image_path)
    before = source_path.stat()
    if not staged_pipeline_enabled(settings, 2, flag="1"):
        raise RuntimeError("Unsupported settings for isolated GPU preflight")

    with Image.open(source_path) as opened:
        source = normalize_page_rgb(opened)
    if profiling:
        stages["gpu_read_normalize"] = perf_counter() - tick
        tick = perf_counter()
    try:
        effective = effective_page_settings(settings, source.size, int(page_index))
        if not bool(getattr(effective, "ordinary_auto_layout", False)):
            raise RuntimeError("Auto-layout not enabled on effective page")
        if bool(getattr(effective, "layout_mask_illustrations", False)):
            raise RuntimeError("Illustration masking needs the serial path")
        analysis = build_analysis_image(source, effective)
        try:
            detector_settings = replace(effective)
            if bool(getattr(detector_settings, "ordinary_auto_columns", False)):
                detector_settings.layout_columns_policy = "detect"
            if profiling:
                stages["gpu_prepare"] = perf_counter() - tick
                tick = perf_counter()
            estimate = detect_layout_parameters(analysis, detector_settings)
            if profiling:
                stages["gpu_layout_detection"] = perf_counter() - tick
                tick = perf_counter()
            expected_size = tuple(analysis.size)
            expected_settings = repr(detector_settings)
        finally:
            if analysis is not source:
                analysis.close()
    finally:
        source.close()
    after = source_path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("Image changed during GPU Layout preflight")
    if profiling:
        stages["gpu_finalize"] = perf_counter() - tick
        record_page(source_path, page_index, stages, stage_group="gpu_preflight")
    return PreparedLayoutEstimate(
        value=estimate,
        page_size=expected_size,
        source_size_bytes=after.st_size,
        source_mtime_ns=after.st_mtime_ns,
        detector_settings_repr=expected_settings,
        page_index=int(page_index),
    )


def verify_prepared_source(
    image_path: str, index: int, prepared: PreparedLayoutEstimate,
) -> None:
    """Fail closed before any CPU calculation/sidecar write on changed image."""
    stat = Path(image_path).stat()
    if (
        prepared.page_index != int(index)
        or stat.st_size != prepared.source_size_bytes
        or stat.st_mtime_ns != prepared.source_mtime_ns
    ):
        raise RuntimeError("Image/preflight identity changed before CPU Layout")


def detect_entries_staged_job(
    image_path: str, settings: Any, pages: tuple[str, str, str],
    profile_page_index: int, prepared: PreparedLayoutEstimate,
) -> int:
    """CPU stage: the original per-page worker with a strict injected estimate."""
    from . import processing

    verify_prepared_source(image_path, profile_page_index, prepared)
    # The actual worker continues to own reading, LayoutRows capture, automatic
    # baseline and PDIC publication. No private graphic/image bytes transmitted.
    return processing.detect_entries_job(
        image_path, settings, pages, profile_page_index,
        prepared_layout=prepared,
    )


__all__ = [
    "PreparedLayoutEstimate", "staged_pipeline_enabled",
    "prepare_gpu_layout_job", "detect_entries_staged_job",
    "use_prepared_layout", "take_prepared_layout", "validate_prepared_layout",
    "verify_prepared_source", "reject_cpu_worker_detector",
]
