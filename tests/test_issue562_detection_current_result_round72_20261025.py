"""Round 72: actual UI-side current-page result application and safeguards."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.models import Entry
from picture_capture.ui.detection_current_page_result import (
    apply_current_page_detection_result,
)


class Var:
    def __init__(self):
        self.value = ""

    def set(self, text):
        self.value = text


class App:
    def __init__(self, project, page):
        self.project = project
        self.current_page = page
        self.entries = [Entry("old-left", 10, 20), Entry("old-right", 70, 40)]
        self.status_var = Var()
        self.events = []

    def _sort_entries_reading_order(self):
        self.events.append("sort")

    def _load_ocr_review_candidates(self):
        self.events.append("load-review")

    def _refresh_page_quality_colors(self):
        self.events.append("colors")

    def _current_page_quality_text(self):
        return "quality-ok"

    def redraw(self):
        self.events.append("redraw")


def run_result(app, *, settings, results, clicked_x=None, stopped=False, error=None):
    return apply_current_page_detection_result(
        app,
        project=app.original_project,
        page=app.original_page,
        settings=settings,
        existing_entries=list(app.original_entries),
        clicked_x=clicked_x,
        stopped=stopped,
        results=results,
        error=error,
        deps={
            "column_index_for_click": lambda x, _geometry: 1 if x >= 40 else 0,
            "column_index": lambda x, _geometry, _y: 1 if x >= 40 else 0,
            "ocr_cache_root": lambda root: root / "OCR",
        },
    )


@pytest.fixture
def workspace(tmp_path):
    page = tmp_path / "page.png"
    project = SimpleNamespace(root=tmp_path, images=[page])
    app = App(project, page)
    app.original_project = project
    app.original_page = page
    app.original_entries = list(app.entries)
    return app


@pytest.mark.parametrize("outcome", ["error", "stopped", "empty", "new_page", "new_project"])
def test_failure_cancel_or_stale_page_does_not_mutate_editor(workspace, outcome):
    before = [(e.word, e.x, e.y) for e in workspace.entries]
    error = RuntimeError("injected") if outcome == "error" else None
    stopped = outcome == "stopped"
    results = [] if outcome == "empty" else [([Entry("new", 70, 42)], object(), None)]
    if outcome == "new_page":
        workspace.current_page = Path("another.png")
    if outcome == "new_project":
        workspace.project = SimpleNamespace(root=Path("different"))
    run_result(
        workspace, settings=SimpleNamespace(detection_method="left_edge"),
        results=results, stopped=stopped, error=error,
    )
    assert [(e.word, e.x, e.y) for e in workspace.entries] == before
    assert workspace.events == []
    assert workspace.status_var.value == ""


def test_clicked_column_replaces_only_that_columns_original_entries(workspace):
    run_result(
        workspace, settings=SimpleNamespace(detection_method="left_edge"),
        results=[([Entry("ignored-left", 15, 23), Entry("fresh", 72, 43)], object(), None)],
        clicked_x=60,
    )
    assert [(e.word, e.x, e.y) for e in workspace.entries] == [
        ("old-left", 10, 20), ("fresh", 72, 43),
    ]
    assert workspace.events == ["sort", "redraw"]
    assert workspace.status_var.value == "智能画线完成：检测到 2 个词条；可手动增删后保存"


def test_combined_completion_preserves_review_and_text_fill_status(workspace):
    run_result(
        workspace, settings=SimpleNamespace(detection_method="combined"),
        results=[([Entry("filled", 9, 12)], object(), {
            "filled": 2, "regular": 1, "large": 1,
        })],
    )
    assert [(e.word, e.x, e.y) for e in workspace.entries] == [("filled", 9, 12)]
    assert workspace.events == ["sort", "load-review", "colors", "redraw"]
    assert "普通救漏自动补字 2 条（普通框 1，大字框 1）" in workspace.status_var.value
    assert "紧凑OCR缓存 page.json" in workspace.status_var.value


def test_controller_uses_canonical_tk_result_owner_without_worker_publication():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture"
    controller = (root / "ui/controllers/detection.py").read_text(encoding="utf-8")
    result = (root / "ui/detection_current_page_result.py").read_text(encoding="utf-8")
    worker = (root / "detection/current_page_worker.py").read_text(encoding="utf-8")
    flow = (root / "ui/detection_current_page_flow.py").read_text(encoding="utf-8")
    assert "return run_current_page_detection(" in controller
    assert 'current["apply_current_page_detection_result"](' in flow
    assert "def apply_current_page_detection_result(" in result
    assert "if app.project is not project or app.current_page != page:" in result
    assert "app._load_ocr_review_candidates()" in result
    assert "app.redraw()" in result
    assert "app.redraw()" not in worker
