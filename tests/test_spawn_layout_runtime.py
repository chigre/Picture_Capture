from __future__ import annotations


def test_core_composition_installs_full_layout_runtime_for_spawn_workers():
    """Explicit core composition must prepare the same physical Layout chain as GUI."""
    from picture_capture.bootstrap.core import build_core_services

    services = build_core_services()
    processing = services.processing
    from picture_capture import dictionary_page_layout_policy as policy
    from picture_capture import layout_physical_indent as physical

    assert bool(getattr(processing, "_pc_spawn_layout_runtime_installed", False))

    # Row recovery is already static before the worker-local runtime entry.
    static_helper = physical._logical_slots_for_oversized_run
    slots = static_helper(0, 400, 40.0)

    # This is exactly the worker-local entry point used before Layout Core runs.
    processing._ensure_layout_runtime()

    assert physical._logical_slots_for_oversized_run is static_helper
    assert len(slots) == 10
    assert bool(getattr(policy, "_column_drift_runtime_installed", False))


def test_spawn_layout_runtime_is_idempotent():
    from picture_capture.bootstrap.core import build_core_services

    processing = build_core_services().processing
    first = processing._ensure_layout_runtime
    processing._ensure_layout_runtime()
    processing._ensure_layout_runtime()
    assert processing._ensure_layout_runtime is first
