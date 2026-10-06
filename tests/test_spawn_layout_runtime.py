from __future__ import annotations

from pathlib import Path


def test_core_composition_keeps_processing_layout_entry_point_static():
    from picture_capture import dictionary_page_design as base
    from picture_capture import layout_physical_indent as physical
    from picture_capture import processing
    from picture_capture.bootstrap.core import build_core_services
    from picture_capture.dictionary_page_design_refined import (
        detect_entries_from_page_design,
    )

    original = processing._ensure_layout_runtime
    static_helper = physical._logical_slots_for_oversized_run
    services = build_core_services()

    assert services.processing is processing
    assert processing._ensure_layout_runtime is original
    assert not hasattr(processing, "_pc_spawn_layout_runtime_installed")

    slots = static_helper(0, 400, 40.0)
    processing._ensure_layout_runtime()

    assert processing._ensure_layout_runtime is original
    assert base.detect_entries_from_page_design is detect_entries_from_page_design
    assert physical._logical_slots_for_oversized_run is static_helper
    assert len(slots) == 10


def test_processing_layout_runtime_remains_observably_idempotent():
    from picture_capture import dictionary_page_design as base
    from picture_capture import processing
    from picture_capture.dictionary_page_design_refined import (
        detect_entries_from_page_design,
    )

    first = processing._ensure_layout_runtime
    processing._ensure_layout_runtime()
    processing._ensure_layout_runtime()

    assert processing._ensure_layout_runtime is first
    assert base.detect_entries_from_page_design is detect_entries_from_page_design


def test_spawn_layout_wrapper_file_is_retired_and_processing_owns_preparation():
    root = Path(__file__).resolve().parents[1]
    runtime = root / "src/picture_capture/spawn_layout_runtime.py"
    processing_source = (
        root / "src/picture_capture/processing.py"
    ).read_text(encoding="utf-8")
    core_source = (
        root / "src/picture_capture/bootstrap/core.py"
    ).read_text(encoding="utf-8")

    assert not runtime.exists()
    assert "def _ensure_layout_runtime()" in processing_source
    assert "dictionary_page_design.detect_entries_from_page_design =" in processing_source
    assert "install_robust_line_starts()" in processing_source
    assert "install_physical_indent_inference()" in processing_source
    assert "spawn_layout_runtime" not in core_source
