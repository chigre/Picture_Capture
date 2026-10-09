from __future__ import annotations

from pathlib import Path

from picture_capture.models import AppSettings


def test_base_page_design_detector_forwards_to_refined_without_runtime(monkeypatch):
    from picture_capture import dictionary_page_design as base
    from picture_capture import dictionary_page_design_refined as refined

    marker = object()
    calls = []

    def fake_refined(image, settings, *, page_index=0, page_sections=None):
        calls.append((image, settings, page_index, page_sections))
        return marker

    monkeypatch.setattr(refined, "detect_entries_from_page_design", fake_refined)
    image = object()
    settings = AppSettings()
    sections = [object()]

    assert base.detect_entries_from_page_design(
        image,
        settings,
        page_index=7,
        page_sections=sections,
    ) is marker
    assert calls == [(image, settings, 7, sections)]


def test_core_composition_keeps_processing_layout_entry_point_static():
    from picture_capture import layout_physical_indent as physical
    from picture_capture import processing
    from picture_capture.bootstrap.core import build_core_services

    original = processing._ensure_layout_runtime
    static_helper = physical._logical_slots_for_oversized_run
    services = build_core_services()

    assert services.processing is processing
    assert processing._ensure_layout_runtime is original
    assert not hasattr(processing, "_pc_spawn_layout_runtime_installed")

    slots = static_helper(0, 400, 40.0)
    processing._ensure_layout_runtime()

    assert processing._ensure_layout_runtime is original
    assert physical._logical_slots_for_oversized_run is static_helper
    assert len(slots) == 10


def test_processing_layout_runtime_remains_observably_idempotent():
    from picture_capture import processing

    first = processing._ensure_layout_runtime
    processing._ensure_layout_runtime()
    processing._ensure_layout_runtime()

    assert processing._ensure_layout_runtime is first


def test_spawn_layout_wrapper_file_is_retired_and_processing_owns_preparation():
    root = Path(__file__).resolve().parents[1]
    runtime = root / "src/picture_capture/spawn_layout_runtime.py"
    processing_source = (
        root / "src/picture_capture/processing.py"
    ).read_text(encoding="utf-8")
    gui_source = (
        root / "src/picture_capture/bootstrap/gui.py"
    ).read_text(encoding="utf-8")
    base_source = (
        root / "src/picture_capture/dictionary_page_design.py"
    ).read_text(encoding="utf-8")
    core_source = (
        root / "src/picture_capture/bootstrap/core.py"
    ).read_text(encoding="utf-8")

    assert not runtime.exists()
    assert "def _ensure_layout_runtime()" in processing_source
    assert "dictionary_page_design.detect_entries_from_page_design =" not in processing_source
    assert "dictionary_page_design.detect_entries_from_page_design =" not in gui_source
    assert "refined_detect_entries(" in base_source
    assert "install_robust_line_starts()" in processing_source
    assert "install_physical_indent_inference()" in processing_source
    assert "spawn_layout_runtime" not in core_source
