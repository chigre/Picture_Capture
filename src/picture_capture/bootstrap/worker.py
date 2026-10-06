from __future__ import annotations

"""Explicit composition root for multiprocessing detection workers.

Shared process-wide runtime preparation is resolved through
``build_core_services`` before worker-specific LayoutRows extensions are added.
The pickleable spawn job therefore consumes one worker profile rather than
reconstructing import-order-sensitive dependencies itself. Bare package import
performs no runtime installation.
"""

from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable


@dataclass(frozen=True)
class WorkerServices:
    """Process-local dependencies used by an ordinary-detection worker."""

    formats: ModuleType
    processing: ModuleType
    capture_layout_rows: Callable[..., Any]
    save_automatic_baseline: Callable[..., Any]


def build_worker_services() -> WorkerServices:
    """Prepare one spawn process and return its explicit worker dependencies.

    The shared core owns common runtime ordering. Worker-local additions remain
    idempotent and preserve the pre-refactor ordinary-detection behavior.
    """
    from .core import build_core_services

    core_services = build_core_services()
    formats = core_services.formats
    processing_module = core_services.processing

    from ..entry_classification import install_pdic_classification
    from ..entry_classification_runtime import install_processing_entry_classification
    from ..layout_rows_cache import (
        capture_layout_rows,
        install_layout_rows_persistence_runtime,
    )
    from ..training_baseline import save_automatic_baseline

    # These calls remain local ordering guards during migration. Core composition
    # already installed the shared classification chain, so they are no-ops in a
    # normally prepared process and preserve historical direct-worker behavior.
    install_pdic_classification(formats)
    install_processing_entry_classification(processing_module)
    # Long-band row recovery and column-drift remeasurement are static.
    install_layout_rows_persistence_runtime()

    return WorkerServices(
        formats=formats,
        processing=processing_module,
        capture_layout_rows=capture_layout_rows,
        save_automatic_baseline=save_automatic_baseline,
    )


__all__ = ["WorkerServices", "build_worker_services"]
