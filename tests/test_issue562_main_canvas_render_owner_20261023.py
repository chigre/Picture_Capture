"""Issue #562 canonical owner and compatibility for main canvas redraw."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

from picture_capture import app as gui
from picture_capture.ui import main_canvas_render_workflow as owner


PKG = Path(__file__).resolve().parents[1] / "src/picture_capture"


def test_main_canvas_full_owner_and_no_heavy_app_import():
    tree = ast.parse((PKG / "ui/main_canvas_render_workflow.py").read_text("utf-8"))
    funcs = {x.name: x for x in tree.body if isinstance(x, ast.FunctionDef)}
    for name in ("redraw", "_draw_crop_plan_preview", "_draw_page_sections",
                 "_draw_review_entry_highlight"):
        assert len(funcs[name].body) > 10
    assert not any(
        isinstance(x, ast.ImportFrom) and x.module in {"app", "processing"}
        for x in ast.walk(tree)
    )


def test_original_tk_signatures_and_forwarding(monkeypatch):
    cls = gui.PictureCaptureApp
    assert list(inspect.signature(cls.redraw).parameters) == ["self"]
    assert list(inspect.signature(cls._draw_crop_plan_preview).parameters) == ["self"]
    for name in ("_draw_page_sections", "_draw_review_entry_highlight"):
        params = list(inspect.signature(getattr(cls, name)).parameters.values())
        assert [p.name for p in params] == ["self", "geometry"]
        assert params[1].default is None
    calls = []
    for name in ("redraw", "_draw_crop_plan_preview", "_draw_page_sections",
                 "_draw_review_entry_highlight"):
        monkeypatch.setattr(
            owner, name,
            lambda self, deps, geometry=None, name=name:
                calls.append((name, self, deps, geometry)),
        )
    fake = SimpleNamespace()
    cls.redraw(fake)
    cls._draw_crop_plan_preview(fake)
    geometry = object()
    cls._draw_page_sections(fake, geometry)
    cls._draw_review_entry_highlight(fake, geometry)
    assert [x[0] for x in calls] == [
        "redraw", "_draw_crop_plan_preview", "_draw_page_sections",
        "_draw_review_entry_highlight"
    ]
    assert all(x[1] is fake and isinstance(x[2], owner.MainCanvasRenderDeps)
               for x in calls)
    assert calls[2][3] is geometry and calls[3][3] is geometry


def test_original_live_dependency_patchpoints(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(gui, "create_alpha_canvas_polygon", sentinel)
    assert gui._main_canvas_render_deps().create_alpha_canvas_polygon is sentinel
    assert len(owner.MainCanvasRenderDeps.__dataclass_fields__) == 18


def test_crop_preview_imports_follow_canonical_location():
    content = (PKG / "ui/main_canvas_render_workflow.py").read_text("utf-8")
    assert "from ..crop.preview_labels import" in content
    assert "from ..crop.preview_display_settings import" in content
    assert "from .illustrated_main_canvas import" in content
