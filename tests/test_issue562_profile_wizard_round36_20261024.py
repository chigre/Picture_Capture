"""Round 36: Profile Wizard multi-page validation physical owner and compatibility tests."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from PIL import Image
from picture_capture.models import AppSettings
from picture_capture.processing import ColumnPath, Geometry
from picture_capture.profile import (
    setup, wizard_validation_execution, wizard_validation_controls, wizard_validation_visuals,
)

ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture/profile"


def test_legacy_validation_method_surfaces_and_real_owner_implementations():
    src = (ROOT / "setup.py").read_text(encoding="utf-8")
    cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "ProjectProfileWizard")
    for method, target in {
        "validate_profile": "_wizard_validation_execution.validate_profile(",
        "_build_validation_tab": "_wizard_validation_controls.build_validation_tab(",
        "_apply_validation_feedback": "_wizard_validation_controls.apply_validation_feedback(",
        "_marker_preview": "_wizard_validation_visuals.marker_preview(",
        "_render_validation_result": "_wizard_validation_visuals.render_validation_result(",
        "_finish_validation": "_wizard_validation_visuals.finish_validation(",
    }.items():
        node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method)
        wrapper = ast.get_source_segment(src, node)
        assert target in wrapper
        assert len(wrapper.splitlines()) < 28
    for file in ("wizard_validation_execution.py", "wizard_validation_controls.py", "wizard_validation_visuals.py"):
        assert "from .setup import" not in (ROOT / file).read_text(encoding="utf-8")
    assert isinstance(inspect.getattr_static(setup.ProjectProfileWizard, "_marker_preview"), staticmethod)


def test_old_validation_entrypoints_keep_live_module_globals(monkeypatch):
    calls = []
    monkeypatch.setattr(wizard_validation_execution, "validate_profile", lambda obj, *, deps: calls.append(("execute", obj, deps)))
    monkeypatch.setattr(wizard_validation_controls, "build_validation_tab", lambda obj, tab, *, deps: calls.append(("tab", obj, tab, deps)))
    monkeypatch.setattr(wizard_validation_controls, "apply_validation_feedback", lambda obj, result: calls.append(("feedback", obj, result)))
    monkeypatch.setattr(wizard_validation_visuals, "marker_preview", lambda *args, deps: calls.append(("marker", args, deps)))
    monkeypatch.setattr(wizard_validation_visuals, "render_validation_result", lambda obj, *, deps: calls.append(("render", obj, deps)))
    monkeypatch.setattr(wizard_validation_visuals, "finish_validation", lambda obj, results: calls.append(("finish", obj, results)))
    obj = setup.ProjectProfileWizard.__new__(setup.ProjectProfileWizard)
    tab = object()
    image = Image.new("RGB", (2, 2), "white")
    obj.validate_profile()
    obj._build_validation_tab(tab)
    obj._apply_validation_feedback("too_many")
    setup.ProjectProfileWizard._marker_preview(image, [], tab, AppSettings(), 0, 320)
    obj._render_validation_result()
    obj._finish_validation([])
    assert [x[0] for x in calls] == ["execute", "tab", "feedback", "marker", "render", "finish"]
    assert calls[0][1] is obj and calls[0][2]["detect_entries"] is setup.detect_entries
    assert calls[0][2]["ProjectProfileWizard"] is setup.ProjectProfileWizard
    assert calls[1][3]["ttk"] is setup.ttk and calls[2][2] == "too_many"
    assert calls[3][2]["ImageDraw"] is setup.ImageDraw
    assert calls[4][2]["themed_display_image"] is setup.themed_display_image
    assert calls[5][2] == []


def test_ocr_validation_keeps_worker_snapshots_forced_refresh_and_ui_handoff():
    owner = (ROOT / "wizard_validation_execution.py").read_text(encoding="utf-8")
    before, remainder = owner.split("    def worker():", 1)
    worker, after = remainder.split("    def done(", 1)
    assert "if self._closing or self._validation_running:" in before
    assert "if self.parent._batch_active:" in before
    assert 'settings.detection_method = "paddleocr"' in before
    assert "settings.paddle_use_paddleocr = True" in before
    assert "paths = {index: project.images[index] for index in indices}" in before
    assert "force_paddle_refresh=True" in worker
    assert "stop_event.is_set()" in worker
    assert "ImageTk.PhotoImage" not in worker
    assert "self._finish_validation(results)" in after
    assert "wait_on_close=True" in after
    assert "save_pdic" not in owner and "write_project_profile" not in owner


def test_translucent_masks_still_operate_through_public_static_preview():
    image = Image.new("RGB", (100, 100), "white")
    geometry = Geometry(
        column_starts=[10], column_widths=[80], top=20, bottom=100,
        column_paths=[ColumnPath([(20, 10), (100, 10)])],
    )
    settings = AppSettings(profile_header_mode="present", profile_header_percent=20.0, profile_footer_mode="none", profile_side_content_mode="none")
    preview = setup.ProjectProfileWizard._marker_preview(image, [], geometry, settings, 0, 100)
    pixel = preview.getpixel((50, 10))
    assert pixel != (255, 215, 0) and pixel != (255, 255, 255)
    assert pixel[0] == 255 and 215 < pixel[1] < 255 and 0 < pixel[2] < 255


def test_feedback_and_results_still_obey_revision_guard():
    owner = (ROOT / "wizard_validation_visuals.py").read_text(encoding="utf-8")
    controls = (ROOT / "wizard_validation_controls.py").read_text(encoding="utf-8")
    assert "self.validation_preview_slot %= len(self._validation_results)" in owner
    assert "ImageTk.PhotoImage(" in owner
    assert "revision_changed = self._validation_revision_started != self._profile_revision" in owner
    assert "self.working.profile_last_validated_pages" in owner
    assert "self._mark_validation_stale()" in controls
    assert "self.cjk_require_left_edge_var.set(True)" in controls
