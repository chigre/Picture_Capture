"""Issue #562 Round 77: legacy direct-action behavior after physical extraction."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.ui.detection_direct_actions import (
    run_current_paddle_action,
    run_all_pages_auto_detect,
    run_legacy_scoped_ocr,
)


class FakeApp:
    def __init__(self):
        self.settings = SimpleNamespace(detection_method="left_edge")
        self.project = SimpleNamespace(images=["one", "two", "three"])
        self.current_index = 1
        self.calls = []
        self.errors = []
        self.guard_ok = True
        self.quick_ok = True

    def guard(self):
        self.calls.append("guard")
        return self.guard_ok

    def apply_quick_settings(self, *, show_status):
        self.calls.append(("quick", show_status))
        return self.quick_ok

    def sync_quick_settings(self):
        self.calls.append("sync")

    def save_settings(self):
        self.calls.append("save")

    def auto_detect_current(self, *, force_paddle_refresh):
        self.calls.append(("current", force_paddle_refresh))

    def _detect_pages(self, indices, *, method, force_refresh):
        self.calls.append(("detect", indices, method, force_refresh))

    def show_error(self, title, error):
        self.errors.append((title, error))


def test_direct_current_paddle_preserves_settings_sync_save_and_refresh():
    app = FakeApp()
    run_current_paddle_action(
        app, force_refresh=True,
        ocr_engine_guard=lambda obj: obj.calls.append("ocr-preflight") or True,
    )
    assert app.settings.detection_method == "paddleocr"
    assert app.calls == [
        "ocr-preflight", "sync", "save", ("current", True),
    ]


@pytest.mark.parametrize("action", ["current", "scoped"])
def test_rejected_ocr_engine_preserves_mode_without_side_effects(action):
    app = FakeApp()
    guard = lambda obj: obj.calls.append("ocr-preflight") or False
    if action == "current":
        run_current_paddle_action(app, force_refresh=False, ocr_engine_guard=guard)
    else:
        run_legacy_scoped_ocr(
            app, scope="all", force_refresh=True, ocr_engine_guard=guard,
        )
    assert app.settings.detection_method == "left_edge"
    assert app.calls == ["ocr-preflight"]
    assert app.errors == []


@pytest.mark.parametrize("scope", ["", "ALL", "selected", "current/all"])
def test_invalid_direct_scope_reports_error_without_mutation_or_dispatch(scope):
    app = FakeApp()
    run_legacy_scoped_ocr(
        app, scope=scope, force_refresh=False,
        ocr_engine_guard=lambda _obj: True,
    )
    assert app.calls == ["guard", ("quick", False)]
    assert app.settings.detection_method == "left_edge"
    assert len(app.errors) == 1
    title, exc = app.errors[0]
    assert title == "页面范围无效" and isinstance(exc, ValueError)


@pytest.mark.parametrize(
    ("scope", "expected"),
    [("current", [1]), ("all", [0, 1, 2])],
)
def test_valid_legacy_ocr_scope_preserves_dispatch_without_settings_save(scope, expected):
    app = FakeApp()
    run_legacy_scoped_ocr(
        app, scope=scope, force_refresh=True,
        ocr_engine_guard=lambda _obj: True,
    )
    assert app.settings.detection_method == "paddleocr"
    assert app.calls == [
        "guard", ("quick", False),
        ("detect", expected, "paddleocr", True),
    ]


def test_legacy_scoped_ocr_quick_settings_failure_does_not_mutate_mode():
    app = FakeApp()
    app.quick_ok = False
    run_legacy_scoped_ocr(
        app, scope="all", force_refresh=True,
        ocr_engine_guard=lambda _obj: True,
    )
    assert app.calls == ["guard", ("quick", False)]
    assert app.settings.detection_method == "left_edge"


def test_batch_auto_detect_preserves_existing_mode_and_refresh():
    app = FakeApp()
    app.settings.detection_method = "combined"
    run_all_pages_auto_detect(app, force_refresh=True)
    assert app.calls == [("detect", [0, 1, 2], "combined", True)]
    assert app.settings.detection_method == "combined"


def test_batch_auto_detect_missing_project_is_noop():
    app = FakeApp()
    app.project = None
    run_all_pages_auto_detect(app, force_refresh=True)
    assert app.calls == []


def test_controller_remains_stable_and_direct_mode_logic_has_physical_owner():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture/ui"
    controller = (root / "controllers/detection.py").read_text(encoding="utf-8")
    direct = (root / "detection_direct_actions.py").read_text(encoding="utf-8")
    for name in ("paddle_detect_current", "batch_auto_detect", "run_ocr_draw"):
        assert f"def {name}(" in controller
    for name in (
        "run_current_paddle_action",
        "run_all_pages_auto_detect",
        "run_legacy_scoped_ocr",
    ):
        assert f"def {name}(" in direct
        assert f"return {name}(" in controller
    assert "app._detect_pages(" in direct
    assert "ocr_engine_guard=guard_ocr_action_selection" in controller
