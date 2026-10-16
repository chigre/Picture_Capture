"""Line-difference bookmarks use recorded automatic positions, not OCR text."""
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from picture_capture.formats import pdic_path, write_pdic
from picture_capture.models import AppSettings, Entry
from picture_capture.training_baseline import baseline_path_for_pdic, save_automatic_baseline
from picture_capture.line_diff_bookmarks import (
    marker_positions,
    page_has_manual_line_difference, modified_line_page_stems,
    bookmark_modified_line_pages,
)
from picture_capture.ui.compact_task_menus import ACTION_GROUPS
from picture_capture.ui.workspace_tools import MACARON_ACTION_COLORS


def _write(page: Path, entries):
    write_pdic(pdic_path(page), entries, 300, (page.stem, "@", "@"))


def test_auto_baseline_then_position_only_changes(tmp_path):
    page = tmp_path / "0001.png"
    Image.new("RGB", (300, 180), "white").save(page)
    initial = [Entry(word="apple", x=10, y=20), Entry(word="banana", x=10, y=60)]
    _write(page, initial)
    assert page_has_manual_line_difference(tmp_path, page) is None
    save_automatic_baseline(pdic_path(page), initial, 300, (page.stem, "@", "@"))
    assert baseline_path_for_pdic(pdic_path(page)).is_file()
    assert page_has_manual_line_difference(tmp_path, page) is False
    # Text-only edits do not make a line difference.
    _write(page, [Entry(word="new", x=10, y=20), Entry(word="other", x=10, y=60)])
    assert page_has_manual_line_difference(tmp_path, page) is False
    _write(page, [Entry(word="new", x=10, y=21), Entry(word="other", x=10, y=60)])
    assert page_has_manual_line_difference(tmp_path, page) is True
    _write(page, [Entry(word="new", x=10, y=20)])
    assert page_has_manual_line_difference(tmp_path, page) is True


def test_only_known_difference_pages_are_marked(tmp_path):
    pages = [tmp_path / f"{n:04}.png" for n in range(3)]
    for page in pages:
        Image.new("RGB", (300, 100), "white").save(page)
        _write(page, [Entry(word="one", x=11, y=20)])
    save_automatic_baseline(pdic_path(pages[0]), [Entry(word="one", x=11, y=20)], 300, (pages[0].stem, "@", "@"))
    save_automatic_baseline(pdic_path(pages[1]), [Entry(word="one", x=11, y=20)], 300, (pages[1].stem, "@", "@"))
    _write(pages[1], [Entry(word="one", x=11, y=24)])
    changed, unknown = modified_line_page_stems(tmp_path, pages)
    assert changed == {pages[1].stem}
    assert unknown == 1


def test_mark_action_preserves_bookmarks_if_no_line_baselines(tmp_path, monkeypatch):
    from picture_capture import line_diff_bookmarks as mod

    page = tmp_path / "one.png"
    Image.new("RGB", (300, 100), "white").save(page)
    settings = AppSettings(page_bookmarks=["saved"])
    settings_path = tmp_path / "settings.json"
    events = []
    monkeypatch.setattr(mod, "settings_path", lambda _root: settings_path)
    from tkinter import messagebox
    monkeypatch.setattr(messagebox, "showwarning", lambda *args, **kwargs: events.append("warning"))
    project = SimpleNamespace(root=tmp_path, images=[page], settings=settings)
    app = SimpleNamespace(
        project=project, settings=settings, _batch_active=False,
        _preprocess_mode_active=lambda: False,
        selected_page_indices=lambda: [0],
        status_var=SimpleNamespace(set=lambda _text: None),
        show_error=lambda *_a: events.append("error"),
    )
    bookmark_modified_line_pages(app)
    assert settings.page_bookmarks == ["saved"]
    assert events == ["warning"]


def test_ui_contract_and_pastel_save_color():
    assert any(("精修画线", "refine_lines_selected_scope") in group
               and ("标记线差异页", "bookmark_modified_line_pages") in group
               for group in ACTION_GROUPS if group)
    assert not any(("保存当前页", "save_current_page") in group
                   for group in ACTION_GROUPS if group)
    assert MACARON_ACTION_COLORS["存"]["light"][0] == "#FFF1B8"
