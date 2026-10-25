"""Round 75: current-page detector preflight and snapshot owner parity."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.models import AppSettings, Entry
from picture_capture.ui.detection_current_page_setup import (
    CurrentPageDetectionSnapshot, prepare_current_page_detection,
)


class Var:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class FakeApp:
    def __init__(self, root: Path, method: str):
        self.project = SimpleNamespace(root=root)
        self.current_page = root / "page.png"
        self.current_index = 3
        self.settings = AppSettings(detection_method=method)
        self.page_sections = ["section"]
        self.entries = [Entry("unsaved", 17, 29)]
        self._batch_active = False
        self.status_var = Var()
        self.events = []
        self.guard_ok = True
        self.geometry_ok = True

    def guard(self):
        self.events.append("guard")
        return self.guard_ok

    def _guard_transformed_geometry(self, title):
        self.events.append(("geometry", title))
        return self.geometry_ok


def deps(events, *, missing=False):
    def check_mask(paths, settings):
        events.append(("mask", paths, settings.detection_method))
        return missing

    return {
        "replace": replace,
        "missing_saved_illustrations": check_mask,
        "ocr_cache_root": lambda root: root / "OCR",
        "headword_filter_rules_path": lambda root, name: root / name,
        "HEADWORD_FILTER_RULES_FILENAME": "headwords.rules",
    }


@pytest.mark.parametrize("mode", ["left_edge", "paddleocr", "combined"])
def test_snapshot_preserves_source_page_section_and_unsaved_markers(tmp_path, mode):
    app = FakeApp(tmp_path, mode)
    events = []
    result = prepare_current_page_detection(app, deps=deps(events))
    assert isinstance(result, CurrentPageDetectionSnapshot)
    assert result.project is app.project
    assert result.page is app.current_page
    assert result.page_index == 3
    assert result.settings is not app.settings
    assert result.settings.detection_method == mode
    assert result.page_sections == ["section"]
    assert result.page_sections is not app.page_sections
    assert [(e.word, e.x, e.y) for e in result.existing_entries] == [
        ("unsaved", 17, 29)
    ]
    assert result.existing_entries[0] is not app.entries[0]
    assert app.events == ["guard", ("geometry", "自动画线")]
    assert events == [("mask", (app.current_page,), mode)]
    if mode == "left_edge":
        assert result.cache_path is None
        assert result.filter_path is None
    else:
        assert result.cache_path == tmp_path / "OCR" / "page.json"
        assert result.filter_path == tmp_path / "headwords.rules"


def test_busy_detection_never_checks_project_or_mask(tmp_path):
    app = FakeApp(tmp_path, "combined")
    app._batch_active = True
    events = []
    assert prepare_current_page_detection(app, deps=deps(events)) is None
    assert app.events == events == []
    assert "后台画线任务运行中" in app.status_var.value


@pytest.mark.parametrize("failing_guard", ["guard", "geometry"])
def test_rejected_guard_never_snapshots_or_checks_mask(tmp_path, failing_guard):
    app = FakeApp(tmp_path, "paddleocr")
    if failing_guard == "guard":
        app.guard_ok = False
    else:
        app.geometry_ok = False
    events = []
    assert prepare_current_page_detection(app, deps=deps(events)) is None
    assert events == []
    if failing_guard == "guard":
        assert app.events == ["guard"]
    else:
        assert app.events == ["guard", ("geometry", "自动画线")]


def test_missing_saved_illustrations_blocks_detection_without_mutation(tmp_path):
    app = FakeApp(tmp_path, "paddleocr")
    initial_settings = app.settings
    initial_entries = list(app.entries)
    events = []
    assert prepare_current_page_detection(app, deps=deps(events, missing=True)) is None
    assert app.settings is initial_settings
    assert app.entries == initial_entries
    assert "当前页缺少 PPP 插图数据" in app.status_var.value


def test_controller_retains_worker_and_callback_while_preflight_moves(tmp_path):
    root = Path(__file__).resolve().parents[1] / "src/picture_capture/ui"
    controller = (root / "controllers/detection.py").read_text(encoding="utf-8")
    setup = (root / "detection_current_page_setup.py").read_text(encoding="utf-8")
    assert "snapshot = prepare_current_page_detection(" in controller
    assert "return detect_current_page(" in controller
    assert "return apply_current_page_detection_result(" in controller
    assert "def prepare_current_page_detection(" in setup
    assert 'deps["missing_saved_illustrations"]((page,), app.settings)' in setup
    assert "existing_entries = [deps[\"replace\"](entry) for entry in app.entries]" in setup
