"""Fixed L/A/S and 图/区/辅 shortcuts share the existing UI mode state."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui import workspace_mode_shortcuts as shortcuts
from picture_capture.ui.controllers.canvas import CanvasController


class Var:
    def __init__(self, value):
        self.value = value
        self.callbacks = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        for callback in tuple(self.callbacks):
            callback(None, None, None)

    def trace_add(self, _mode, callback):
        self.callbacks.append(callback)


class Button:
    def __init__(self):
        self.styles = {}

    def winfo_exists(self):
        return True

    def configure(self, **kwargs):
        self.styles.update(kwargs)


def _flags():
    app = SimpleNamespace(
        polygon_draw_var=Var(False),
        auxiliary_mode_var=Var(False),
        _section_editing=False,
        _layout_visualization_var=Var(False),
        crop_preview_var=Var(False),
        ocr_crop_preview_var=Var(False),
        display_mode_var=Var("原图+标注"),
        hide_var=Var(False),
        binary_preview_var=Var(False),
        appearance_mode="light",
        _main_ui_colors={
            "button": "#FFFFFF", "text": "#222222", "button_hover": "#DDDDDD",
        },
        workspace_mode_shortcut_buttons={
            key: Button() for key in shortcuts.MODE_TOOLTIPS
        },
        status_var=SimpleNamespace(set=lambda _message: None),
        _display_mode_syncing=False,
        photo=None,
        _display_photo_cache_key=None,
        redraw=lambda: None,
    )
    controller = CanvasController(app)
    app._display_mode_from_flags = controller.display_mode_from_flags
    app._apply_display_mode = controller.apply_display_mode
    return app


def test_mode_selected_reads_original_flags_not_private_button_flags():
    app = _flags()
    assert all(not shortcuts.mode_shortcut_selected(app, label)
               for label in shortcuts.MODE_TOOLTIPS)
    app.polygon_draw_var.set(True)
    app._section_editing = True
    app.auxiliary_mode_var.set(True)
    app._layout_visualization_var.set(True)
    app.crop_preview_var.set(True)
    app.ocr_crop_preview_var.set(True)
    assert all(shortcuts.mode_shortcut_selected(app, label)
               for label in shortcuts.MODE_TOOLTIPS)


def test_selected_orange_and_theme_inactive_state_sync_with_original_menu_vars():
    app = _flags()
    shortcuts.install_workspace_mode_shortcut_traces(app)
    inactive = app.workspace_mode_shortcut_buttons["L"].styles["bg"]
    assert inactive == "#FFFFFF"
    app._layout_visualization_var.set(True)  # Menu action, not header click.
    orange = app.workspace_mode_shortcut_buttons["L"].styles["bg"]
    assert orange == shortcuts.SELECTED_COLORS["light"][0]
    app.appearance_mode = "dark"
    shortcuts.refresh_workspace_mode_shortcut_buttons(app)
    assert app.workspace_mode_shortcut_buttons["L"].styles["bg"] == (
        shortcuts.SELECTED_COLORS["dark"][0]
    )
    app._layout_visualization_var.set(False)
    assert app.workspace_mode_shortcut_buttons["L"].styles["bg"] == inactive
    # Installing traces again must not duplicate callbacks.
    shortcuts.install_workspace_mode_shortcut_traces(app)
    assert len(app._layout_visualization_var.callbacks) == 1


def test_a_s_share_exclusive_display_mode_and_restore_prior_nonpreview_mode():
    app = _flags()
    app.display_mode_var.set("仅二值")
    app._apply_display_mode()
    shortcuts.toggle_workspace_display_preview(app, "切图预览")
    assert app.display_mode_var.get() == "切图预览"
    assert shortcuts.mode_shortcut_selected(app, "A")
    assert not shortcuts.mode_shortcut_selected(app, "S")
    shortcuts.toggle_workspace_display_preview(app, "OCR词头区域预览")
    assert not shortcuts.mode_shortcut_selected(app, "A")
    assert shortcuts.mode_shortcut_selected(app, "S")
    shortcuts.toggle_workspace_display_preview(app, "OCR词头区域预览")
    assert app.display_mode_var.get() == "仅二值"
    assert not shortcuts.mode_shortcut_selected(app, "A")
    assert not shortcuts.mode_shortcut_selected(app, "S")
    assert app.binary_preview_var.get() is True


def test_l_uses_original_exclusive_hide_and_restores_visibility():
    app = _flags()
    app.hide_var.set(True)
    shortcuts.toggle_workspace_layout(app)
    assert app._layout_visualization_var.get() is True
    assert app.hide_var.get() is True
    assert app._layout_visualization_snapshot_key is None
    shortcuts.toggle_workspace_layout(app)
    assert app._layout_visualization_var.get() is False
    assert app.hide_var.get() is True
    app.hide_var.set(False)
    shortcuts.toggle_workspace_layout(app)
    assert app.hide_var.get() is True
    shortcuts.toggle_workspace_layout(app)
    assert app.hide_var.get() is False


def test_editor_buttons_invoke_original_commands_and_are_toggleable():
    app = _flags()
    events = []

    def polygon_toggle():
        app.polygon_draw_var.set(not app.polygon_draw_var.get())
        events.append("polygon")

    def aux_toggle():
        events.append("auxiliary")

    def finish_section():
        events.append("finish-section")
        app._section_editing = False

    app.toggle_polygon_drawing = polygon_toggle
    app.toggle_auxiliary_mode = aux_toggle
    app._finish_section_editing = finish_section
    app.toggle_current_page_section_editing = lambda: events.append("section")

    shortcuts.toggle_workspace_illustration_editor(app)
    assert app.polygon_draw_var.get()
    shortcuts.toggle_workspace_illustration_editor(app)
    assert not app.polygon_draw_var.get()

    shortcuts.toggle_workspace_section_editor(app)
    assert events[-1] == "section"
    app._section_editing = True
    shortcuts.toggle_workspace_auxiliary_editor(app)
    assert not app._section_editing and app.auxiliary_mode_var.get()
    assert events[-2:] == ["finish-section", "auxiliary"]
    shortcuts.toggle_workspace_illustration_editor(app)
    assert not app.auxiliary_mode_var.get() and app.polygon_draw_var.get()
    assert events[-2:] == ["auxiliary", "polygon"]


def test_same_section_dialog_is_shared_by_page_double_click_and_shortcut(monkeypatch):
    import picture_capture.app as app_module

    calls = []
    page = Path("page001.png")
    app = SimpleNamespace(
        project=SimpleNamespace(images=[page]),
        current_index=0,
        _section_editing=False,
        polygon_draw_var=Var(False),
        auxiliary_mode_var=Var(False),
        _preprocess_mode_active=lambda: False,
        _finish_section_editing=lambda: calls.append("finish"),
        _set_page_section_count=lambda index, count: calls.append((index, count)),
        status_var=SimpleNamespace(set=lambda text: calls.append(text)),
    )
    monkeypatch.setattr(app_module, "read_page_sections", lambda _page: [])
    monkeypatch.setattr(
        app_module.simpledialog, "askinteger",
        lambda *args, **kwargs: 2,
    )
    app_module.PictureCaptureApp._edit_page_section_index(app, 0)
    assert calls == [(0, 2)]
    app._section_editing = True
    app_module.PictureCaptureApp._edit_page_section_index(app, 0)
    assert calls[-1] == "finish"


def test_shortcuts_are_located_and_wired_in_permanent_main_toolbar():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    source = (root / "ui" / "workspace_tools.py").read_text(encoding="utf-8")
    app = (root / "app.py").read_text(encoding="utf-8")
    for label in ("图", "区", "辅", "L", "A", "S"):
        assert f'("{label}", ' in source
        assert label in shortcuts.MODE_TOOLTIPS
    for text in (
        "编辑插图",
        "编辑Section区域；双击页面列表相应位置亦可进入该编辑模式",
        "编辑辅助线；SHIFT+左键=画辅助线",
    ):
        assert text in shortcuts.MODE_TOOLTIPS.values()
    assert 'theme_toggle.pack(side="left", padx=(0, 2))' in source
    assert 'row=9 + index if extreme else 3' in source
    assert "refresh_workspace_mode_shortcut_buttons(self)" in app
    assert "app.workspace_edit_shortcut_buttons.append(button)" in source
