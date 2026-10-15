"""Review crop-side sequence badges: same style/format as main canvas labels.

Mock Tk tests verify widget ownership, lower-edge alignment, zoom gutter and
row teardown. The existing ReviewWindow delete path is exercised by its R3/B2
regressions; no pixel scans, PDIC schema, or OCR guesses are introduced.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.ui import review_crop_sequence as sequence


class Widget:
    def __init__(self, parent, **kwargs):
        self.parent = parent
        self.options = kwargs
        self.grid_args = None
        self.bindings = {}
        self.children = []
        self.alive = True
        if hasattr(parent, "children"):
            parent.children.append(self)

    def grid(self, **kwargs):
        self.grid_args = kwargs

    def bind(self, event, handler):
        self.bindings[event] = handler

    def destroy(self):
        self.alive = False
        for child in self.children:
            child.destroy()


class Label(Widget):
    pass


class Frame(Widget):
    def columnconfigure(self, *_args, **_kwargs):
        pass


class FakeFont:
    def __init__(self, root=None, font=None):
        self.spec = font

    def measure(self, text):
        return len(text) * 9


def _fixture(total=120):
    settings = SimpleNamespace(
        main_entry_font_family="Auto", main_entry_font_size=16,
        main_entry_follow_zoom=False,
        ocr_language="chi_sim",
    )
    app = SimpleNamespace(
        settings=settings, image=SimpleNamespace(width=1400),
        view_scale=1.0, entries=[object()] * total,
        _entry_sequence_text=lambda i, n: str(i).zfill(len(str(max(1, n)))),
    )
    review = SimpleNamespace(
        parent=app, scroll_rows=lambda *_: None,
        scroll_rows_linux=lambda *_: None,
    )
    rows = Frame(None)
    return review, rows


@pytest.fixture
def fake_tk(monkeypatch):
    monkeypatch.setattr(sequence.ttk, "Frame", Frame)
    monkeypatch.setattr(sequence.ttk, "Label", Label)
    monkeypatch.setattr(sequence.tk, "Label", Label)
    monkeypatch.setattr(sequence.font, "Font", FakeFont)
    monkeypatch.setattr(sequence, "fixed_overlay_control_font", lambda *_: ("Arial", 9, "bold"))


def test_review_crop_sequence_reuses_main_format_and_style_bottom_aligned(fake_tk):
    review, rows = _fixture()
    picture, badge, container = sequence.create_review_crop_with_index(
        review, rows, photo=object(), index=7, total=120,
    )
    assert badge.options["text"] == "007"  # main zero-based, page-wide padding
    assert badge.options["bg"] == "#e6e6e6"
    assert badge.options["fg"] == "#000000"
    assert badge.options["bd"] == 0
    assert badge.options["padx"] == 2
    assert badge.options["pady"] == 0
    assert badge.options["font"] == ("Arial", 9, "bold")
    assert badge._pc_skip_classic_appearance is True
    assert badge.grid_args["column"] == 0
    assert badge.grid_args["sticky"] == "s"
    assert picture.grid_args["column"] == 1
    assert picture.grid_args["row"] == 0
    assert container.grid_args["row"] == 14
    assert container.grid_args["column"] == 0
    assert picture.parent is container
    assert badge.parent is container
    assert all(e in badge.bindings for e in ("<MouseWheel>", "<Button-4>", "<Button-5>"))


@pytest.mark.parametrize("total,index,expected", [
    (1, 0, "0"), (10, 9, "09"), (100, 99, "099"), (100, 0, "000"),
])
def test_review_sequence_has_same_zero_based_padding_as_main(fake_tk,total,index,expected):
    review, rows = _fixture(total)
    _picture, badge, _host = sequence.create_review_crop_with_index(
        review, rows, photo=object(), index=index, total=total,
    )
    assert badge.options["text"] == expected


def test_deleting_row_destroys_crop_badge_and_rebuilds_updated_numbers(fake_tk):
    review, rows = _fixture(12)
    pairs = [
        sequence.create_review_crop_with_index(
            review, rows, photo=object(), index=i, total=12,
        )
        for i in range(12)
    ]
    # ReviewWindow.render_rows destroys all direct row children following
    # its committed [X] deletion and re-enumerates saved Entry identities.
    for child in list(rows.children):
        child.destroy()
    assert all(not badge.alive and not picture.alive for picture,badge,_host in pairs)
    after = [
        sequence.create_review_crop_with_index(
            review, rows, photo=object(), index=i, total=11,
        )
        for i in range(11)
    ]
    assert [badge.options["text"] for _,badge,_ in after] == [
        f"{i:02d}" for i in range(11)
    ]
    assert len(after) == 11


def test_auto_zoom_reserves_badge_width_for_last_page_index(fake_tk):
    review, _rows = _fixture(120)
    assert sequence.review_sequence_gutter(review) == 3 * 9 + 4 + 3
    review.parent.entries = []
    assert sequence.review_sequence_gutter(review) == 0


def test_render_and_delete_bindings_stay_in_existing_review_window():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "app.py"
    ).read_text("utf-8")
    render = source.split("    def render_rows(", 1)[1].split(
        "\n    def _candidate_for_entry(", 1,
    )[0]
    remove = source.split("    def delete_review_entry(", 1)[1].split(
        "\n    def _save_digit_map(", 1,
    )[0]
    assert "create_review_crop_with_index(" in render
    assert "picture, sequence_label, crop_row =" in render
    assert "self._review_row_pictures.append(picture)" in render
    assert "for child in self.rows.winfo_children():" in render
    assert "child.destroy()" in render
    assert "self.parent.entries.remove(entry)" in remove
    assert "self._request_render_rows(focus_index=self.active_index)" in remove


def test_sequence_font_does_not_change_with_zoom_or_editor_settings(fake_tk):
    review, rows = _fixture()
    _pic, badge, _host = sequence.create_review_crop_with_index(
        review, rows, photo=object(), index=1, total=120,
    )
    review.parent.view_scale = 4.0
    review.parent.settings.main_entry_font_size = 39
    review.parent.settings.main_entry_font_family = "DifferentUserFont"
    _pic2, badge2, _host2 = sequence.create_review_crop_with_index(
        review, rows, photo=object(), index=1, total=120,
    )
    assert badge.options["font"] == badge2.options["font"] == ("Arial", 9, "bold")
