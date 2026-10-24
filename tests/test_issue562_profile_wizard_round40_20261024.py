"""Round 40: Lifecycle bootstrap and template column interactions physically extracted."""
from __future__ import annotations

import ast
import inspect
import math
from pathlib import Path
from types import SimpleNamespace

from picture_capture.profile import setup, wizard_bootstrap, wizard_template_interactions

ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture/profile"

TEMPLATE_METHODS = (
    "_selected_column_index",
    "_column_offsets_for_count",
    "_refresh_column_adjust_status",
    "_update_template_column_highlight",
    "_nudge_template_column_preview",
    "_shift_selected_column",
    "_reset_selected_column",
    "_reset_all_column_offsets",
    "_preview_path_distance_sq",
    "_select_template_column",
    "_refresh_template_controls",
    "_move_template_preview",
)


def test_round40_bootstrap_super_remains_on_wizard_and_lifecycle_physically_moves():
    source = (ROOT / "setup.py").read_text(encoding="utf-8")
    owner = (ROOT / "wizard_bootstrap.py").read_text(encoding="utf-8")
    klass = next(x for x in ast.parse(source).body if isinstance(x, ast.ClassDef) and x.name == "ProjectProfileWizard")
    init = next(x for x in klass.body if isinstance(x, ast.FunctionDef) and x.name == "__init__")
    body = ast.get_source_segment(source, init)
    assert "super().__init__(parent)" in body
    assert "_wizard_bootstrap.initialize_wizard(" in body
    assert "super().__init__(parent)" not in owner
    assert list(inspect.signature(setup.ProjectProfileWizard.__init__).parameters) == ["self", "parent", "new_project"]
    assert inspect.signature(setup.ProjectProfileWizard.__init__).parameters["new_project"].kind is inspect.Parameter.KEYWORD_ONLY
    assert "self._closing = False" in owner
    assert "self._validation_stop_event = threading.Event()" in owner
    assert "self.sample_indices = representative_page_indices(" in owner
    assert "self._build_vars()" in owner and "self._build_ui()" in owner
    assert "self._show_sample_loading_state()" in owner
    assert "self.after(20, self._start_sample_thumbnail_load)" in owner
    assert owner.index("self._build_vars()") < owner.index("self._build_ui()") < owner.index("self._show_sample_loading_state()")
    assert "from .setup import" not in owner


def test_round40_initialization_calls_toplevel_first_with_original_live_globals(monkeypatch):
    calls = []
    def base_init(obj, parent):
        calls.append(("super", obj, parent))
    def moved_init(obj, parent, *, new_project, deps):
        calls.append(("owner", obj, parent, new_project, deps))
    monkeypatch.setattr(setup.tk.Toplevel, "__init__", base_init)
    monkeypatch.setattr(wizard_bootstrap, "initialize_wizard", moved_init)
    parent = object()
    obj = setup.ProjectProfileWizard.__new__(setup.ProjectProfileWizard)
    obj.__init__(parent, new_project=True)
    assert [entry[0] for entry in calls] == ["super", "owner"]
    assert calls[0][1:] == (obj, parent)
    assert calls[1][1:4] == (obj, parent, True)
    deps = calls[1][4]
    for name in ("replace", "_screen_work_area", "ImageTk", "queue", "threading",
                 "suggested_body_page_range", "configured_body_page_indices",
                 "probable_body_page_indices", "representative_page_indices"):
        assert deps[name] is getattr(setup, name)


def test_round40_all_template_methods_stay_on_class_with_original_signatures():
    source = (ROOT / "setup.py").read_text(encoding="utf-8")
    owner = (ROOT / "wizard_template_interactions.py").read_text(encoding="utf-8")
    owner_nodes = {x.name for x in ast.parse(owner).body if isinstance(x, ast.FunctionDef)}
    klass = next(x for x in ast.parse(source).body if isinstance(x, ast.ClassDef) and x.name == "ProjectProfileWizard")
    methods = {x.name: x for x in klass.body if isinstance(x, ast.FunctionDef)}
    for name in TEMPLATE_METHODS:
        moved = name.lstrip("_")
        assert moved in owner_nodes
        block = ast.get_source_segment(source, methods[name])
        assert "_wizard_template_interactions." + moved + "(" in block
        assert len(block.splitlines()) < 20
    assert any(isinstance(node, ast.Name) and node.id == "staticmethod" for node in methods["_preview_path_distance_sq"].decorator_list)
    assert list(inspect.signature(setup.ProjectProfileWizard._preview_path_distance_sq).parameters) == ["points", "x", "y"]
    assert list(inspect.signature(setup.ProjectProfileWizard._select_template_column).parameters) == ["self", "event", "line_paths"]
    assert "from .setup import" not in owner


def test_round40_live_template_delegates_and_mathematics(monkeypatch):
    calls = []
    monkeypatch.setattr(wizard_template_interactions, "refresh_template_controls", lambda obj, *, deps: calls.append(("refresh", obj, deps)))
    monkeypatch.setattr(wizard_template_interactions, "nudge_template_column_preview", lambda obj, index, delta, *, deps: calls.append(("nudge", obj, index, delta, deps)))
    stub = setup.ProjectProfileWizard.__new__(setup.ProjectProfileWizard)
    stub._refresh_template_controls()
    stub._nudge_template_column_preview(2, -4)
    assert calls[0][0] == "refresh" and calls[0][2]["SIDE_LABEL_TO_VALUE"] is setup.SIDE_LABEL_TO_VALUE
    assert calls[1][0:4] == ("nudge", stub, 2, -4)
    assert calls[1][4]["tk"] is setup.tk
    assert math.isinf(setup.ProjectProfileWizard._preview_path_distance_sq([], 0, 0))
    assert setup.ProjectProfileWizard._preview_path_distance_sq([(1.0, 2.0)], 1.0, 2.0) == 0
    assert setup.ProjectProfileWizard._preview_path_distance_sq([(0.0, 0.0), (10.0, 0.0)], 5.0, 3.0) == 9


def test_round40_offsets_keep_pixel_units_and_ui_line_only_nudge():
    class V:
        def __init__(self, value): self.value = value
        def get(self): return self.value
    changes = []
    stub = SimpleNamespace(
        columns_var=V(2),
        working=SimpleNamespace(column_width=800, column_start_offsets=[0, 0]),
        selected_column_index=0,
    )
    stub._selected_column_index = lambda: wizard_template_interactions.selected_column_index(stub)
    stub._column_offsets_for_count = lambda count=None: wizard_template_interactions.column_offsets_for_count(stub, count)
    stub._refresh_column_adjust_status = lambda: changes.append("status")
    stub._nudge_template_column_preview = lambda i, delta: changes.append(("move", i, delta))
    stub._profile_input_changed = lambda *, refresh_preview: changes.append(("profile", refresh_preview))
    wizard_template_interactions.shift_selected_column(stub, +1)
    assert stub.working.column_start_offsets == [1, 0]
    assert changes == ["status", ("move", 0, 1), ("profile", False)]
    changes.clear()
    wizard_template_interactions.reset_selected_column(stub)
    assert stub.working.column_start_offsets == [0, 0]
    assert changes == ["status", ("move", 0, -1), ("profile", False)]
    stub.working.column_start_offsets = [2, -5]
    changes.clear()
    wizard_template_interactions.reset_all_column_offsets(stub)
    assert stub.working.column_start_offsets == [0, 0]
    assert changes == [("move", 0, -2), ("move", 1, 5), "status", ("profile", False)]


def test_round40_template_controls_respond_to_header_footer_and_alternating_sides():
    class V:
        def __init__(self, value): self.value = value
        def get(self): return self.value
    class W:
        def __init__(self): self.state = None
        def configure(self, **kwargs): self.state = kwargs["state"]
    attrs = {key: W() for key in (
        "columns_spin", "header_percent_spin", "footer_percent_spin",
        "side_percent_spin", "side_percent_a_spin", "side_percent_b_spin",
        "first_variant_combo",
    )}
    stub = SimpleNamespace(**attrs, header_mode_var=V("yes"), footer_mode_var=V("no"), side_mode_var=V("alternate"))
    wizard_template_interactions.refresh_template_controls(stub, deps={
        "tk": setup.tk,
        "HEADER_LABEL_TO_VALUE": {"yes": "present"},
        "FOOTER_LABEL_TO_VALUE": {"no": "auto"},
        "SIDE_LABEL_TO_VALUE": {"alternate": "outer"},
    })
    assert stub.columns_spin.state == "normal"
    assert stub.header_percent_spin.state == "normal"
    assert stub.footer_percent_spin.state == "disabled"
    assert stub.side_percent_spin.state == "disabled"
    assert stub.side_percent_a_spin.state == "normal"
    assert stub.side_percent_b_spin.state == "normal"
    assert stub.first_variant_combo.state == "readonly"
