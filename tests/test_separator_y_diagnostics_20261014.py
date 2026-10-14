"""Read-only per-line Layout Y refinement diagnostics stay synchronized with real output."""
import inspect

from picture_capture import processing, separator_y_refinement


def test_refiner_exposes_optional_diagnostics_without_changing_default_signature():
    sig = inspect.signature(separator_y_refinement.refined_layout_entry_y_by_line)
    assert sig.parameters["diagnostics"].default is None
    assert sig.parameters["page_index"].default == 0


def test_layout_materializer_forwards_diagnostics_without_changing_normal_path():
    source = inspect.getsource(processing._ordinary_entries_from_layout_roles)
    assert "diagnostics=diagnostics" in source
    assert "canonical_y = int(refined_y_by_line.get(" in source


def test_replay_preserves_raw_refinement_and_clamp_separately():
    source = inspect.getsource(separator_y_refinement.refined_layout_entry_y_by_line)
    assert "raw_refined = int(refined)" in source
    assert "raw_refined_y" in source
    assert "clamped_y" in source
    assert "roi_x0" in source and "roi_x1" in source
    assert "search_top" in source and "search_bottom" in source
    assert "except Exception as exc:" in source


def test_replay_has_dedicated_y_refinement_stage():
    source = inspect.getsource(processing.detect_entries)
    assert "separator_y_per_line" in source
    assert "横线 Y 精修诊断（逐条）" in source
