from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui.controllers.canvas import CanvasController


ROOT = Path(__file__).resolve().parents[1]


class _Var:
    def __init__(self, value=None) -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


class _Canvas:
    def __init__(self) -> None:
        self.xscroll: list[tuple[int, str]] = []
        self.yscroll: list[tuple[int, str]] = []
        self.xmoves: list[float] = []
        self.ymoves: list[float] = []
        self.deleted: list[str] = []
        self.rectangles: list[tuple[tuple, dict]] = []
        self.lines: list[tuple[tuple, dict]] = []
        self.texts: list[tuple[tuple, dict]] = []
        self.raised: list[str] = []

    def winfo_width(self) -> int:
        return 1024

    def winfo_height(self) -> int:
        return 824

    def xview_scroll(self, amount: int, units: str) -> None:
        self.xscroll.append((amount, units))

    def yview_scroll(self, amount: int, units: str) -> None:
        self.yscroll.append((amount, units))

    def xview_moveto(self, value: float) -> None:
        self.xmoves.append(value)

    def yview_moveto(self, value: float) -> None:
        self.ymoves.append(value)

    def canvasx(self, value: float) -> float:
        return value + 10

    def canvasy(self, value: float) -> float:
        return value + 20

    def delete(self, tag: str) -> None:
        self.deleted.append(tag)

    def create_rectangle(self, *args, **kwargs):
        self.rectangles.append((args, kwargs))
        return len(self.rectangles)

    def create_line(self, *args, **kwargs):
        self.lines.append((args, kwargs))
        return len(self.lines)

    def create_text(self, *args, **kwargs):
        self.texts.append((args, kwargs))
        return len(self.texts)

    def tag_raise(self, tag: str) -> None:
        self.raised.append(tag)


class _Popup:
    def __init__(self) -> None:
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


class _App:
    def __init__(self) -> None:
        self.binary_preview_var = _Var(False)
        self.hide_var = _Var(False)
        self.crop_preview_var = _Var(False)
        self.display_mode_var = _Var("原图+标注")
        self.status_var = _Var("")
        self.cursor_status_var = _Var("")
        self.view_zoom_var = _Var("100%")
        self.quick_bool_vars = {"show_rulers": _Var(True)}
        self.settings = SimpleNamespace(show_rulers=True, ruler_color="#1976d2")
        self.appearance_mode = "light"
        self._main_ui_colors = {}
        self._display_mode_syncing = False
        self._section_editing = False
        self._preprocess_active = False
        self._ruler_hint = None
        self.cursor_canvas_xy = None
        self.entries = [object(), object()]
        self.photo = object()
        self._display_photo_cache_key = ("cached",)
        self.view_scale = 1.0
        self.image = SimpleNamespace(width=1000, height=2000)
        self.canvas = _Canvas()
        self.redraw_calls = 0
        self.idle_status_calls = 0
        self.update_idle_calls = 0

    def redraw(self) -> None:
        self.redraw_calls += 1

    def _set_idle_cursor_status(self) -> None:
        self.idle_status_calls += 1

    def _hide_ruler_hint(self) -> None:
        CanvasController(self).hide_ruler_hint()

    def _update_view_zoom_label(self) -> None:
        self.view_zoom_var.set(f"{round(self.view_scale * 100):d}%")

    def _preprocess_mode_active(self) -> bool:
        return self._preprocess_active

    def update_idletasks(self) -> None:
        self.update_idle_calls += 1


def test_display_mode_mapping_and_apply_preserve_existing_semantics() -> None:
    app = _App()
    controller = CanvasController(app)

    assert controller.display_mode_from_flags() == "原图+标注"
    app.binary_preview_var.set(True)
    assert controller.display_mode_from_flags() == "二值+标注"
    app.hide_var.set(True)
    assert controller.display_mode_from_flags() == "仅二值"
    app.binary_preview_var.set(False)
    assert controller.display_mode_from_flags() == "仅原图"
    app.crop_preview_var.set(True)
    assert controller.display_mode_from_flags() == "切图预览"

    app.display_mode_var.set("二值+标注")
    app.crop_preview_var.set(False)
    app.hide_var.set(True)
    controller.apply_display_mode()
    assert app.binary_preview_var.get() is True
    assert app.hide_var.get() is False
    assert app.crop_preview_var.get() is False
    assert app.photo is None
    assert app._display_photo_cache_key is None
    assert app.redraw_calls == 1
    assert app._display_mode_syncing is False


def test_preview_toggles_keep_modes_exclusive_and_invalidate_only_when_needed() -> None:
    app = _App()
    controller = CanvasController(app)

    controller.toggle_binary_preview()
    assert app.photo is None
    assert app._display_photo_cache_key is None
    assert app.display_mode_var.get() == "原图+标注"

    app.photo = object()
    app._display_photo_cache_key = ("cached",)
    app.hide_var.set(True)
    app.crop_preview_var.set(True)
    controller.toggle_hide_overlays()
    assert app.crop_preview_var.get() is False
    assert app.display_mode_var.get() == "仅原图"
    assert app.photo is not None

    app.binary_preview_var.set(True)
    app.crop_preview_var.set(True)
    controller.toggle_crop_preview()
    assert app.binary_preview_var.get() is False
    assert app.hide_var.get() is False
    assert app.photo is None
    assert app._display_photo_cache_key is None
    assert app.display_mode_var.get() == "切图预览"
    assert "切图预览" in app.status_var.get()


def test_ruler_visibility_drawing_and_hit_testing_preserve_page_edge_semantics() -> None:
    app = _App()
    controller = CanvasController(app)

    assert controller.rulers_visible() is True
    controller.draw_percentage_rulers()
    assert len(app.canvas.rectangles) == 3
    assert any(call[1].get("tags") == ("ruler-margin",) for call in app.canvas.rectangles)
    assert any("measurement-ruler" in call[1].get("tags", ()) for call in app.canvas.lines)
    assert any(call[1].get("text") == "50" for call in app.canvas.texts)

    assert controller.ruler_hit_id(0, 500) == "left"
    assert controller.ruler_hit_id(999, 500) == "right"
    assert controller.ruler_hit_id(500, 0) == "top"
    assert controller.ruler_hit_id(500, 1999) == "bottom"
    assert controller.ruler_hit_id(500, 500) is None

    app.hide_var.set(True)
    assert controller.rulers_visible() is True
    assert controller.ruler_hit_id(0, 0) in {"left", "top"}


def test_ruler_hint_hide_and_cursor_guides_keep_cleanup_contracts() -> None:
    app = _App()
    controller = CanvasController(app)

    popup = _Popup()
    app._ruler_hint = popup
    controller.hide_ruler_hint()
    assert popup.destroyed is True
    assert app._ruler_hint is None

    controller.draw_cursor_guides(200, 300)
    assert app.canvas.deleted[-1] == "cursor-guide"
    assert len(app.canvas.lines) == 2
    assert app.canvas.raised[-1] == "cursor-guide"

    before = len(app.canvas.lines)
    app._section_editing = True
    controller.draw_cursor_guides(200, 300)
    assert len(app.canvas.lines) == before

    app._section_editing = False
    app.cursor_canvas_xy = (10.0, 20.0)
    controller.canvas_leave(None)
    assert app.cursor_canvas_xy is None
    assert app.canvas.deleted[-1] == "cursor-guide"
    assert app.idle_status_calls == 1


def test_idle_cursor_status_keeps_normal_and_preprocess_wording() -> None:
    app = _App()
    controller = CanvasController(app)

    app.view_scale = 1.25
    controller.set_idle_cursor_status()
    assert app.cursor_status_var.get() == "坐标：—｜缩放 125%｜词条 2"

    app._preprocess_active = True
    controller.set_idle_cursor_status()
    assert app.cursor_status_var.get() == "坐标：—｜预处理预览｜缩放 125%"


def test_zoom_text_and_fit_operations_preserve_clamps_and_view_reset() -> None:
    app = _App()
    controller = CanvasController(app)

    controller.zoom(10.0)
    assert app.view_scale == 3.0
    assert app.view_zoom_var.get() == "300%"
    assert app.redraw_calls == 1
    assert app.idle_status_calls == 1

    app.view_zoom_var.set("1%")
    controller.apply_view_zoom_text()
    assert app.view_scale == 0.08
    assert app.view_zoom_var.get() == "8%"

    app.view_zoom_var.set("n/a")
    redraw_before = app.redraw_calls
    controller.apply_view_zoom_text()
    assert app.redraw_calls == redraw_before
    assert app.view_zoom_var.get() == "8%"

    controller.fit_page_width()
    assert app.view_scale == 1.0
    assert app.canvas.xmoves == [0.0]

    controller.fit_page_height()
    assert app.view_scale == 0.4
    assert app.canvas.ymoves == [0.0]
    assert app.update_idle_calls == 2


def test_canvas_scroll_and_coordinate_mapping_remain_compatible() -> None:
    app = _App()
    app.view_scale = 2.0
    controller = CanvasController(app)

    assert controller.canvas_mousewheel(SimpleNamespace(delta=120)) == "break"
    assert app.canvas.yscroll[-1] == (-3, "units")
    assert controller.canvas_shift_mousewheel(SimpleNamespace(delta=-120)) == "break"
    assert app.canvas.xscroll[-1] == (3, "units")

    assert controller.canvas_linux_mousewheel(SimpleNamespace(state=0), 1) == "break"
    assert app.canvas.yscroll[-1] == (3, "units")
    assert controller.canvas_linux_mousewheel(SimpleNamespace(state=0x0001), -1) == "break"
    assert app.canvas.xscroll[-1] == (-3, "units")

    assert controller.original_xy(SimpleNamespace(x=30, y=40)) == (20, 30)
    before = app.view_scale
    assert controller.canvas_ctrl_mousewheel(SimpleNamespace(delta=120)) == "break"
    assert app.view_scale > before


def test_canvas_controller_has_no_reverse_dependency_on_app_module() -> None:
    path = ROOT / "src/picture_capture/ui/controllers/canvas.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_canvas_controller_wiring_keeps_picture_capture_app_compatibility_methods() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller = (ROOT / "src/picture_capture/ui/controllers/canvas.py").read_text(encoding="utf-8")

    imports = app[: app.index("class PictureCaptureApp")]
    assert "CanvasController" in imports
    assert "self.canvas_controller = CanvasController(self)" in app
    assert "def _canvas_controller_for_call(" in app
    assert 'self.__dict__.get("canvas_controller")' in app
    assert app.index("self.canvas_controller = CanvasController(self)") < app.index("self._build_ui()")

    expected = {
        "_display_mode_from_flags": "display_mode_from_flags",
        "_sync_display_mode_from_flags": "sync_display_mode_from_flags",
        "_apply_display_mode": "apply_display_mode",
        "_toggle_binary_preview": "toggle_binary_preview",
        "_toggle_hide_overlays": "toggle_hide_overlays",
        "_toggle_crop_preview": "toggle_crop_preview",
        "_rulers_visible": "rulers_visible",
        "_draw_percentage_rulers": "draw_percentage_rulers",
        "_ruler_hit_id": "ruler_hit_id",
        "_hide_ruler_hint": "hide_ruler_hint",
        "_show_ruler_hint": "show_ruler_hint",
        "_update_view_zoom_label": "update_view_zoom_label",
        "zoom": "zoom",
        "apply_view_zoom_text": "apply_view_zoom_text",
        "fit_page_width": "fit_page_width",
        "fit_page_height": "fit_page_height",
        "canvas_mousewheel": "canvas_mousewheel",
        "canvas_shift_mousewheel": "canvas_shift_mousewheel",
        "canvas_ctrl_mousewheel": "canvas_ctrl_mousewheel",
        "canvas_linux_mousewheel": "canvas_linux_mousewheel",
        "original_xy": "original_xy",
        "draw_cursor_guides": "draw_cursor_guides",
        "canvas_leave": "canvas_leave",
        "_set_idle_cursor_status": "set_idle_cursor_status",
    }
    for app_method, controller_method in expected.items():
        assert f"def {app_method}(" in app
        assert f"self._canvas_controller_for_call().{controller_method}" in app
        assert f"def {controller_method}(" in controller
