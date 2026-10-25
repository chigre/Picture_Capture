"""Issue #562 Round 45: physical shared-observation and Profile scroll owners."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from picture_capture import paddle_headwords, processing
from picture_capture.models import AppSettings, Entry
from picture_capture.profile import setup
from picture_capture.detection import shared_observations
from picture_capture.profile import wizard_scroll

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_round45_physical_owners_and_legacy_signatures():
    facade = ast.parse((ROOT / "processing/__init__.py").read_text(encoding="utf-8"))
    old = next(n for n in facade.body if isinstance(n, ast.FunctionDef)
               and n.name == "_shared_detector_observations")
    assert len(old.body) <= 2
    owner = ast.parse((ROOT / "detection/shared_observations.py").read_text(encoding="utf-8"))
    actual = next(n for n in owner.body if isinstance(n, ast.FunctionDef)
                  and n.name == "shared_detector_observations")
    assert len(actual.body) > 6
    assert processing._shared_detector_observations.__module__ == "picture_capture.processing"
    assert "paddle_cache_path" in inspect.signature(processing._shared_detector_observations).parameters

    wizard = next(n for n in ast.parse((ROOT / "profile/setup.py").read_text(encoding="utf-8")).body
                  if isinstance(n, ast.ClassDef) and n.name == "ProjectProfileWizard")
    for name in ("_active_tab_canvas", "_is_widget_descendant",
                 "_wizard_mousewheel", "_wizard_linux_wheel"):
        old_method = next(n for n in wizard.body
                          if isinstance(n, ast.FunctionDef) and n.name == name)
        assert len(old_method.body) <= 2
        assert getattr(setup.ProjectProfileWizard, name).__module__ == "picture_capture.profile.setup"
    physical = ast.parse((ROOT / "profile/wizard_scroll.py").read_text(encoding="utf-8"))
    assert sum(isinstance(n, ast.FunctionDef) for n in physical.body) == 4


def test_round45_shared_ocr_and_combined_live_hooks(monkeypatch, tmp_path):
    image = Image.new("RGB", (50, 60), "white")
    settings = AppSettings()
    understanding = SimpleNamespace(page_settings=settings)
    geometry = object()
    calls = []
    monkeypatch.setattr(processing._core, "normalize_page_rgb",
                        lambda source: (calls.append("normalize") or source))
    monkeypatch.setattr(processing._core, "effective_page_settings",
                        lambda s, size, idx: (calls.append(("effective", size, idx)) or s))
    monkeypatch.setattr(processing, "_page_template_image",
                        lambda source, s, idx: (calls.append("template") or source))
    monkeypatch.setattr(processing, "_geometry_from_page_understanding",
                        lambda obj: (calls.append("geometry") or geometry))
    monkeypatch.setattr(processing, "_review_candidates_from_cache",
                        lambda path: [{"id": 7}])
    monkeypatch.setattr(processing, "_ordinary_settings_for_shared_geometry",
                        lambda s, g, *, method: (calls.append(method) or s))
    ordinary = Entry(word="ordinary", x=2, y=3)
    ocr = Entry(word="ocr", x=4, y=5)
    # The public processing facade mirrors this assignment into core.
    # Register the core's original value *before* patching the facade so
    # monkeypatch's reverse-order undo restores both historical identities.
    monkeypatch.setattr(processing._core, "_detect_entries_left_edge",
                        processing._original_detect_entries_left_edge)
    monkeypatch.setattr(processing, "_detect_entries_left_edge",
                        lambda source, s, *, page_sections: ([ordinary], geometry))
    monkeypatch.setattr(processing._core, "_fuse_detection_entries",
                        lambda vb, paddle, g, s, sections, *, review_candidates, image:
                        (calls.append(("fusion", review_candidates)) or [*vb, *paddle]))
    monkeypatch.setattr(paddle_headwords, "detect_paddle_headwords",
                        lambda source, g, s, **kwargs: [ocr])

    def run(method):
        return processing._shared_detector_observations(
            image, understanding, method,
            paddle_cache_path=tmp_path / "cache.json",
            force_paddle_refresh=False,
            paddle_filter_rules_path=None,
            profile_page_index=9, page_sections=None,
        )
    rows, got_geometry, review = run("paddleocr")
    assert rows == [ocr] and got_geometry is geometry and review == [{"id": 7}]
    rows, got_geometry, review = run("combined")
    assert rows == [ordinary, ocr] and got_geometry is geometry
    assert review == [{"id": 7}]
    assert ("effective", (50, 60), 9) in calls
    assert ("fusion", [{"id": 7}]) in calls
    assert "combined" in calls
    rows, got_geometry, review = run("other")
    assert rows == [] and got_geometry is geometry and review == []


def test_round45_wizard_scroll_routes_and_static_ancestry():
    events = []
    left = SimpleNamespace(yview_scroll=lambda delta, unit: events.append(("left", delta, unit)))
    right = SimpleNamespace(yview_scroll=lambda delta, unit: events.append(("right", delta, unit)))
    child = object()
    host = object()
    wizard = SimpleNamespace(
        right_canvas=right, right_content=host,
        _is_widget_descendant=lambda widget, ancestor: widget is child and ancestor is host,
        _active_tab_canvas=lambda: left,
    )
    assert setup.ProjectProfileWizard._wizard_mousewheel(
        wizard, SimpleNamespace(widget=child, delta=120)) == "break"
    assert setup.ProjectProfileWizard._wizard_mousewheel(
        wizard, SimpleNamespace(widget=object(), delta=-120)) == "break"
    assert setup.ProjectProfileWizard._wizard_mousewheel(
        wizard, SimpleNamespace(widget=child, delta=0)) is None
    assert setup.ProjectProfileWizard._wizard_linux_wheel(
        wizard, SimpleNamespace(widget=child), -1) == "break"
    assert setup.ProjectProfileWizard._wizard_linux_wheel(
        wizard, SimpleNamespace(widget=object()), 1) == "break"
    assert events == [("right", -3, "units"), ("left", 3, "units"),
                      ("right", -3, "units"), ("left", 3, "units")]

    class Node:
        def __init__(self, parent=None):
            self.parent = parent
        def winfo_parent(self):
            return "parent" if self.parent else ""
        def _nametowidget(self, name):
            assert name == "parent"
            return self.parent
    root = Node()
    child_node = Node(root)
    assert setup.ProjectProfileWizard._is_widget_descendant(child_node, root)
    assert not setup.ProjectProfileWizard._is_widget_descendant(root, child_node)
    notebook = SimpleNamespace(select=lambda: "selected", index=lambda selected: 1)
    fake = SimpleNamespace(notebook=notebook, tab_canvases=[left, right])
    assert setup.ProjectProfileWizard._active_tab_canvas(fake) is right
    fake.tab_canvases = []
    assert setup.ProjectProfileWizard._active_tab_canvas(fake) is None
