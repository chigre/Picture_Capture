"""PPP caption widget positioning and visibility switch regression tests."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_ppp_label_is_above_figure_aligned_left():
    import ast
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PictureCaptureApp")
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_external_polygon_label_position")
    namespace = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<test>", "exec"), namespace)
    position = namespace["_external_polygon_label_position"]
    assert position(50, 100, 240, 290, 80, 22, 400, 600) == (50, 72)
    assert position(350, 100, 390, 290, 80, 22, 400, 600) == (318, 72)
    # At the top of the page, fall back inside the canvas rather than
    # giving the Entry widget a negative/offscreen y coordinate.
    assert position(50, 8, 240, 290, 80, 22, 400, 600) == (50, 14)


def test_ppp_label_visibility_is_respected_in_edit_mode_and_applied_immediately():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'show_labels = bool(self.settings.show_illustration_labels)' in source
    assert 'show_illustration_labels or self.polygon_draw_var.get()' not in source
    assert 'command=lambda: self._apply_overlay_visibility_toggle("show_illustration_labels", label_visible_var)' in source
