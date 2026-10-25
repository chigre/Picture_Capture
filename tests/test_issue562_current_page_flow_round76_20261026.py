"""Issue #562 Round 76: real current-page scheduling owns callback lifetimes.

These tests call the extracted UI flow directly, independently of the existing
controller tests. Heavy detection/OCR are spies rather than native inference.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.ui.detection_current_page_flow import run_current_page_detection


class FakeApp:
    def __init__(self):
        self.jobs = []

    def _start_batch_task(self, title, indices, worker, done, **kwargs):
        self.jobs.append((title, indices, worker, done, kwargs))


def make_case(tmp_path: Path, method: str):
    app = FakeApp()
    settings = SimpleNamespace(detection_method=method)
    project = SimpleNamespace(root=tmp_path)
    page = tmp_path / "original-page.png"
    snapshot = SimpleNamespace(
        project=project, page=page, page_index=4, settings=settings,
        page_sections=["section"], existing_entries=["unsaved"],
        cache_path=tmp_path / "cache.json" if method != "left_edge" else None,
        filter_path=tmp_path / "rules" if method != "left_edge" else None,
    )
    calls = []

    def prepare(received_app, *, deps):
        assert received_app is app
        assert "missing_saved_illustrations" in deps
        assert "replace" in deps
        calls.append(("prepare",))
        return snapshot

    def inference(*args, **kwargs):
        calls.append(("inference", args, kwargs))
        return ["detected"], "geometry", {"filled": 1}

    def publish(*args, **kwargs):
        calls.append(("publish", args, kwargs))

    deps = {
        "prepare_current_page_detection": prepare,
        "replace": object(),
        "missing_saved_illustrations": object(),
        "ocr_cache_root": object(),
        "headword_filter_rules_path": object(),
        "HEADWORD_FILTER_RULES_FILENAME": "headwords.rules",
        "detect_current_page": inference,
        "Image": object(),
        "normalize_page_rgb": object(),
        "detect_entries": object(),
        "detection_mask_source_path": object(),
        "ocr_existing_entry_words_from_markers": object(),
        "load_replace_rules": object(),
        "replace_rules_path": object(),
        "project_profile_path": object(),
        "apply_current_page_detection_result": publish,
        "column_index_for_click": object(),
        "column_index": object(),
    }
    return app, snapshot, deps, calls


@pytest.mark.parametrize(
    ("method", "label", "refresh"),
    [
        ("left_edge", "当前页自动画线", False),
        ("paddleocr", "OCR画线 当前页识别", True),
        ("combined", "融合画线 当前页识别", True),
    ],
)
def test_current_page_flow_preserves_scope_mode_and_worker_arguments(
    tmp_path, method, label, refresh,
):
    app, snap, deps, calls = make_case(tmp_path, method)
    run_current_page_detection(
        app, clicked_x=42, force_paddle_refresh=True,
        dependencies=lambda: deps,
    )
    assert calls == [("prepare",)]
    assert len(app.jobs) == 1
    title, indices, worker, done, opts = app.jobs[0]
    assert (title, indices, opts["refresh_page_quality"]) == (label, [4], refresh)
    assert opts["item_label"](4) == "original-page.png"

    result = worker(4, 1, 1)
    assert result == (["detected"], "geometry", {"filled": 1})
    name, args, kwargs = calls[1]
    assert name == "inference"
    assert args == (snap.page, snap.project.root, snap.settings)
    assert kwargs["page_index"] == 4
    assert kwargs["page_sections"] == ["section"]
    assert kwargs["cache_path"] == snap.cache_path
    assert kwargs["filter_path"] == snap.filter_path
    assert kwargs["force_paddle_refresh"] is True
    assert "detect_entries" in kwargs["deps"]

    done(1, 1, False, [result], None)
    name, args, kwargs = calls[2]
    assert name == "publish" and args == (app,)
    assert kwargs["project"] is snap.project
    assert kwargs["page"] is snap.page
    assert kwargs["settings"] is snap.settings
    assert kwargs["existing_entries"] == ["unsaved"]
    assert kwargs["clicked_x"] == 42
    assert kwargs["results"] == [result]
    assert kwargs["error"] is None and kwargs["stopped"] is False


def test_worker_and_completion_resolve_fresh_controller_dependencies(tmp_path):
    app, _snapshot, live, calls = make_case(tmp_path, "combined")
    reads = []
    def dependencies():
        reads.append("read")
        return live

    run_current_page_detection(
        app, clicked_x=None, force_paddle_refresh=False,
        dependencies=dependencies,
    )
    _, _, worker, done, _ = app.jobs[0]
    initial = len(reads)
    live["detect_current_page"] = lambda *args, **kwargs: ("late", "geometry", None)
    assert worker(4, 1, 1) == ("late", "geometry", None)
    assert len(reads) == initial + 1
    committed = []
    live["apply_current_page_detection_result"] = (
        lambda *args, **kwargs: committed.append(kwargs["results"])
    )
    done(1, 1, False, [("late", "geometry", None)], None)
    assert len(reads) == initial + 2
    assert committed == [[("late", "geometry", None)]]
    assert calls == [("prepare",)]


def test_refused_preflight_does_not_schedule_or_dispatch(tmp_path):
    app, _, live, calls = make_case(tmp_path, "paddleocr")
    live["prepare_current_page_detection"] = (
        lambda _app, *, deps: calls.append(("refused",)) or None
    )
    run_current_page_detection(
        app, clicked_x=12, force_paddle_refresh=False,
        dependencies=lambda: live,
    )
    assert calls == [("refused",)]
    assert app.jobs == []


def test_flow_retains_stable_tk_entry_and_does_not_perform_inference_itself():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture"
    controller = (root / "ui/controllers/detection.py").read_text(encoding="utf-8")
    flow = (root / "ui/detection_current_page_flow.py").read_text(encoding="utf-8")
    worker = (root / "detection/current_page_worker.py").read_text(encoding="utf-8")
    assert "def auto_detect_current(" in controller
    assert "return run_current_page_detection(" in controller
    assert 'current["detect_current_page"](' in flow
    assert 'current["apply_current_page_detection_result"](' in flow
    assert "app._start_batch_task(" in flow
    assert 'deps["detect_entries"](' in worker
    assert "app.redraw()" not in worker
