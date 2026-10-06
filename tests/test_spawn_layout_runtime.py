from __future__ import annotations

from pathlib import Path


def test_core_composition_keeps_worker_layout_preparation_without_column_drift_patch():
    from picture_capture.bootstrap.core import build_core_services

    services = build_core_services()
    processing = services.processing
    from picture_capture import dictionary_page_layout_policy as policy
    from picture_capture import layout_physical_indent as physical

    assert bool(getattr(processing, "_pc_spawn_layout_runtime_installed", False))
    assert not bool(getattr(policy, "_column_drift_runtime_installed", False))

    static_helper = physical._logical_slots_for_oversized_run
    slots = static_helper(0, 400, 40.0)
    first = processing._ensure_layout_runtime
    processing._ensure_layout_runtime()

    assert processing._ensure_layout_runtime is first
    assert physical._logical_slots_for_oversized_run is static_helper
    assert len(slots) == 10

    policy_source = (
        Path(__file__).resolve().parents[1]
        / "src/picture_capture/dictionary_page_layout_policy.py"
    ).read_text(encoding="utf-8")
    assert "finalize_layout_column_drift(" in policy_source


def test_spawn_layout_runtime_is_idempotent():
    from picture_capture.bootstrap.core import build_core_services

    processing = build_core_services().processing
    first = processing._ensure_layout_runtime
    processing._ensure_layout_runtime()
    processing._ensure_layout_runtime()
    assert processing._ensure_layout_runtime is first
