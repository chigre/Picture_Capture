"""The hide-line-frame switch must affect entry overlays only."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_hide_overlays_only_guards_entry_drawing():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PictureCaptureApp")
    redraw = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "redraw")
    section = ast.get_source_segment(source, redraw)
    assert section is not None
    start = section.index("hidden = bool(self.hide_var.get())")
    end = section.index("show_shapes =")
    visible = section[start:end]
    assert "if not hidden:" in visible
    before_entry, after_entry = visible.split("if not hidden:", 1)
    assert "_draw_review_entry_highlight(geometry)" in before_entry
    assert "_draw_page_sections(geometry)" in before_entry
    assert "_draw_percentage_rulers(geometry)" in before_entry
    assert "show_guides" in before_entry
    assert "show_candidates" in after_entry
    assert "_draw_entry_overlay(" in after_entry
    assert "overlay_scale = self.view_scale / parameter_scale" in before_entry
    assert "if hidden and self._section_editing:" not in visible


def test_ruler_visibility_independent_of_hidden_entry_overlays():
    source = (ROOT / "ui" / "controllers" / "canvas.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "CanvasController")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "rulers_visible")
    segment = ast.get_source_segment(source, method)
    assert "return bool(visible)" in segment
    assert "hide_var" not in segment
