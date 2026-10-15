"""No dangerous saved XY changes from the explicit refinement button."""
from dataclasses import dataclass
from pathlib import Path
import json
import pytest
from picture_capture import marker_refinement_guard as guard
from picture_capture.simplified_review import entry_key


@dataclass
class Row:
    word: str
    x: int
    y: int


def test_refinement_validates_count_text_duplicates_and_bounds(tmp_path):
    page = tmp_path / "p.png"
    before = [Row("first", 10, 12), Row("second", 10, 36)]
    guard.validate_refined_markers(page, before, [Row("first", 10, 13), Row("second", 10, 35)], (100, 100))
    with pytest.raises(ValueError, match="重复"):
        guard.validate_refined_markers(page, before, [Row("first", 10, 20), Row("second", 10, 20)], (100, 100))
    with pytest.raises(ValueError, match="边界"):
        guard.validate_refined_markers(page, before, [Row("first", 10, 101), before[1]], (100, 100))
    with pytest.raises(ValueError, match="文字"):
        guard.validate_refined_markers(page, before, [Row("different", 10, 12), before[1]], (100, 100))


def test_refinement_refuses_paired_and_malformed_sidecar(monkeypatch, tmp_path):
    page = tmp_path / "scan.png"
    sidecar = tmp_path / "simplified.json"
    sidecar.write_text(json.dumps({"format": "picture_capture_simplified_review", "entries": []}), encoding="utf-8")
    monkeypatch.setattr(guard, "simplified_review_path_for_image", lambda _: sidecar)
    monkeypatch.setattr(guard, "read_records", lambda _: {entry_key(10, 12): {"word": "abc"}})
    with pytest.raises(ValueError, match="简体"):
        guard.validate_refined_markers(page, [Row("abc", 10, 12)], [Row("abc", 10, 13)], (100, 100))
    sidecar.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="简体"):
        guard.validate_refined_markers(page, [Row("abc", 10, 12)], [Row("abc", 10, 13)], (100, 100))


def test_refine_button_has_settings_hint_and_shared_y_engine():
    src = Path(__file__).parents[1] / "src" / "picture_capture"
    app = (src / "app.py").read_text(encoding="utf-8")
    menu = (src / "ui/compact_task_menus.py").read_text(encoding="utf-8")
    core = (src / "processing_core.py").read_text(encoding="utf-8")
    assert "请先去设置中心的精修Y调整参数" in app
    assert "请先去设置中心的精修Y调整参数" in menu
    assert "settings.paddle_refine_separator_y = True" in app
    assert "refine_existing_entries(" in app
    assert "refine_separator_y(" in core
    assert "validate_refined_markers(" in app
