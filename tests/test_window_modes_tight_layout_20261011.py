"""New layout regression tests for upper-right modes and narrow page range."""
from pathlib import Path

from picture_capture.ui.workspace_tools import compact_page_column_widths

SRC = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "ui"


def test_mode_buttons_at_upper_right_keep_os_caption():
    text = (SRC / "workspace_tools.py").read_text(encoding="utf-8")
    assert 'mode_bar.pack(side="top", fill="x", before=app.main_paned)' in text
    assert 'mode_group.pack(side="right")' in text
    assert 'for caption in ("极简", "紧凑", "正常")' in text
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
