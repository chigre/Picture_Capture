from __future__ import annotations

from picture_capture import formats, processing
from picture_capture.bootstrap.worker import WorkerServices, build_worker_services
from picture_capture.layout_rows_cache import capture_layout_rows
from picture_capture.training_baseline import save_automatic_baseline


def test_worker_bootstrap_returns_explicit_process_local_dependencies() -> None:
    services = build_worker_services()

    assert isinstance(services, WorkerServices)
    assert services.formats is formats
    assert services.processing is processing
    assert services.capture_layout_rows is capture_layout_rows
    assert services.save_automatic_baseline is save_automatic_baseline


def test_worker_bootstrap_is_idempotent_for_repeated_jobs() -> None:
    first = build_worker_services()
    second = build_worker_services()

    assert first.formats is second.formats is formats
    assert first.processing is second.processing is processing
    assert first.capture_layout_rows is second.capture_layout_rows
    assert first.save_automatic_baseline is second.save_automatic_baseline
    assert bool(getattr(processing, "_entry_classification_runtime_installed", False))
