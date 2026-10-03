from __future__ import annotations


def test_core_composition_installs_full_layout_runtime_for_spawn_workers():
    """Explicit core composition must prepare the same physical Layout chain as GUI."""
    from picture_capture.bootstrap.core import build_core_services

    services = build_core_services()
    processing = services.processing
    from picture_capture import dictionary_page_layout_policy as policy
    from picture_capture import layout_physical_indent as physical

    assert bool(getattr(processing, "_pc_spawn_layout_runtime_installed", False))

    # This is exactly the worker-local entry point used before Layout Core runs.
    processing._ensure_layout_runtime()

    assert bool(getattr(physical, "_long_band_row_recovery_installed", False))
    assert bool(getattr(policy, "_column_drift_runtime_installed", False))


def test_spawn_layout_runtime_is_idempotent():
    from picture_capture.bootstrap.core import build_core_services

    processing = build_core_services().processing
    first = processing._ensure_layout_runtime
    processing._ensure_layout_runtime()
    processing._ensure_layout_runtime()
    assert processing._ensure_layout_runtime is first
