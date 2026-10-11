"""New layout regression tests for upper-right modes and narrow page range."""
from pathlib import Path

from picture_capture.ui.workspace_tools import compact_page_column_widths

SRC = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "ui"


def test_mode_buttons_at_upper_right_keep_os_caption():
    text = (SRC / "workspace_tools.py").read_text(encoding="utf-8")
    assert 'mode_bar.pack(side="top", fill="x", before=app.main_paned)' in text
    assert 'mode_group.pack(side="right")' in text
    assert 'for caption in ("极简", "紧凑", "正常", "最大")' in text
    assert 'project_group.pack(side="right", padx=(0, 3))' in text
    assert 'app.after_idle(lambda: install_header_quick_controls(app))' in text
    assert 'app.workspace_header_quick_host = ttk.Frame(mode_bar' in text
    assert 'rail, 0, "☰", "工具菜单"' not in text
    assert 'app._attach_tooltip(text_button, tip)' not in text
    assert 'app.project_action_bar = project_group' in text
    assert 'app.workspace_header_project_buttons.append((button, label, symbol))' in text
    assert 'app.project_footer_buttons.append(button)' in text
    assert 'button.state(["selected"] if mode == active else ["!selected"])' in text
    assert 'overrideredirect(' not in text


def test_compact_page_columns_fit_a_120px_rail():
    columns = ("bookmark", "page", "section", "lined", "fill_status", "illustrations")
    labels = dict(zip(columns, ("●", "页面", "域", "线", "填充状态", "图")))
    rows = [("●", "long_dictionary_filename_1001", "2", "●", "已填充", "●")]
    shown = ("bookmark", "page", "lined", "illustrations")
    sizes = compact_page_column_widths(
        labels, rows, columns, shown, 120, lambda value: len(value) * 7,
    )
    assert 36 <= sizes["page"] <= 100
    assert sizes["bookmark"] <= 22 and sizes["lined"] <= 22
    assert sizes["illustrations"] <= 22
    assert sum(sizes[column] for column in shown) <= 102


def test_page_range_radio_buttons_share_one_row_with_small_entry():
    controls = (SRC / "simple_page_controls.py").read_text(encoding="utf-8")
    workspace = (SRC / "workspace_tools.py").read_text(encoding="utf-8")
    for radio in ('(0, "当前", "current")', '(1, "至末页", "to_end")',
                  '(2, "至指定", "to_specified")'):
        assert radio in controls
    assert '.grid(row=0, column=column, sticky="w", padx=0, pady=0)' in controls
    assert 'value="specified", style="PC.Workspace80.TRadiobutton"' in controls
    assert 'style="PC.Workspace80.TEntry"' in controls
    assert 'indicatorsize=10' in workspace


def test_project_shortcuts_adapt_to_narrow_width_without_rebuilding_buttons():
    from types import SimpleNamespace

    from picture_capture.ui.workspace_tools import _refresh_header_project_labels

    class Button:
        def __init__(self):
            self.calls = []

        def configure(self, **kwargs):
            self.calls.append(kwargs)

    class Frame:
        def __init__(self):
            self.events = []

        def pack(self, **kwargs):
            self.events.append(("pack", kwargs))

        def pack_forget(self):
            self.events.append(("hide", {}))

    buttons = [Button() for _ in range(4)]
    labels = ("项目", "Profile", "设置", "帮助")
    symbols = ("▣", "◈", "⚙", "?")
    mode_separator, quick_host, project_separator, project = [Frame() for _ in range(4)]
    app = SimpleNamespace(
        workspace_header_project_buttons=list(zip(buttons, labels, symbols)),
        workspace_header_mode_separator=mode_separator,
        workspace_header_quick_host=quick_host,
        workspace_header_project_separator=project_separator,
        project_action_bar=project,
    )
    _refresh_header_project_labels(app, 320)
    assert [button.calls[-1]["text"] for button in buttons] == list(symbols)
    assert all(button.calls[-1]["width"] == 2 for button in buttons)
    assert not any(action == "pack" for action, _ in quick_host.events)
    assert not any(action == "pack" for action, _ in project.events)
    _refresh_header_project_labels(app, 320)
    assert all(len(button.calls) == 1 for button in buttons)
    _refresh_header_project_labels(app, 720)
    assert quick_host.events[-1][0] == "pack"
    assert project.events[-1][0] == "pack"
    assert [button.calls[-1]["text"] for button in buttons] == list(symbols)
    _refresh_header_project_labels(app, 1200)
    assert [button.calls[-1]["text"] for button in buttons] == list(labels)
    assert all(button.calls[-1]["width"] == 7 for button in buttons)
    assert quick_host.events[-1][0] == "pack"


def test_header_actions_share_view_zoom_var_and_preserve_bottom_toolbar():
    text = (SRC / "workspace_tools.py").read_text(encoding="utf-8")
    section = text.split("def install_header_quick_controls(", 1)[1].split(
        "def _refresh_window_mode_buttons(", 1
    )[0]
    assert 'textvariable=app.view_zoom_var, width=5' in section
    assert 'widget.bind("<Return>", app.apply_view_zoom_text)' in section
    assert 'widget.bind("<FocusOut>", app.apply_view_zoom_text)' in section
    for callback in ('app.zoom(0.87)', 'app.zoom(1.15)',
                     'app.fit_page_width', 'app.fit_page_height',
                     'app.fit_single_column_width', 'app.run_normal_draw_action',
                     'app.run_ocr_draw_action', 'app.open_review'):
        assert callback in section
    assert 'app.workspace_quick_actions_host = quick_host' in text
    assert 'app.after_idle(lambda: install_compact_zoom_controls(app))' in text
    assert 'app.workspace_quick_action_buttons.append(button)' in text
    assert 'app.workspace_quick_zoom_controls.append(widget)' in text
