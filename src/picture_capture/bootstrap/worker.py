from __future__ import annotations

"""Explicit composition root for multiprocessing detection workers.

This module owns the worker-local runtime preparation that historically lived
inside ``spawn_detection_runtime.detect_entries_job_with_runtime``.  It is kept
lazy on purpose: character-height recovery must be installed before importing
``picture_capture.processing`` because Page Understanding modules can capture
layout callables by value during import.

Package-wide import-time installers still exist in ``picture_capture.__init__``
at this stage.  Removing those side effects is a separate migration step after
both GUI and worker composition roots are explicit and covered by tests.
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

    The installer order intentionally matches the pre-refactor worker target.
    Installers are idempotent, so calling this for each submitted job preserves
    the historical semantics while removing composition ownership from the job
    function itself.
    """

    # Must happen before importing processing: its Page Understanding chain may
    # bind detect_layout_parameters by value during module import.
    from ..layout_character_height_runtime import (
        install_character_height_fallback_runtime,
    )

    install_character_height_fallback_runtime()

    from .. import formats
    from .. import processing as processing_module
    from ..entry_classification import install_pdic_classification
    from ..entry_classification_runtime import install_processing_entry_classification
    from ..layout_column_drift_runtime import install_layout_column_drift_runtime
    from ..layout_row_recovery_runtime import install_layout_row_recovery_runtime
    from ..layout_rows_cache import (
        capture_layout_rows,
        install_layout_rows_persistence_runtime,
    )
    from ..training_baseline import save_automatic_baseline

    install_pdic_classification(formats)
    install_processing_entry_classification(processing_module)
    install_layout_row_recovery_runtime()
    # Keep column-drift installation after row recovery, matching the historical
    # GUI and worker ordering. The physical-indent finalizer remains idempotent.
    install_layout_column_drift_runtime()
    install_layout_rows_persistence_runtime()

    return WorkerServices(
        formats=formats,
        processing=processing_module,
        capture_layout_rows=capture_layout_rows,
        save_automatic_baseline=save_automatic_baseline,
    )


__all__ = ["WorkerServices", "build_worker_services"]
