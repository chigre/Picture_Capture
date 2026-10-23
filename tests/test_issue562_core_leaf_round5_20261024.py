"""Issue #562: reading-order and OCR line-grouping leaf compatibility."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from picture_capture import processing as public_processing
from picture_capture import processing_core as pc
from picture_capture import paddle_headwords as public_paddle
from picture_capture import paddle_headwords_core as ph
from picture_capture.geometry import reading_order
from picture_capture.ocr import line_grouping
from picture_capture.models import Entry
from picture_capture.ocr.headword_models import OCRRecord, OCRLine

PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def _geometry():
    return SimpleNamespace(
        top=0, bottom=250,
        column_starts=[10, 110], column_widths=[70, 70],
        column_paths=[object(), object()],
        source_to_canonical=lambda x, y: (x, y),
        x_at=lambda i, y: (10 if i == 0 else 110 + y // 10),
    )


def test_leaf_modules_present_and_core_signatures_and_model_origins_unchanged():
    assert (PKG / "geometry/reading_order.py").is_file()
    assert (PKG / "ocr/line_grouping.py").is_file()
    assert not (PKG / "reading_order.py").exists()
    assert not (PKG / "line_grouping.py").exists()
    assert len(list(PKG.glob("*.py"))) == 10
    for fn in (pc.column_index_for_click, pc.entry_reading_order_key,
               pc.sort_entries_reading_order, pc.sort_entries_column_y):
        assert fn.__module__ == "picture_capture.processing_core"
    for fn in (ph._vertical_overlap, ph.group_ocr_records, ph._merge_ocr_lines):
        assert fn.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(pc.column_index_for_click).parameters) == [
        "x", "geometry", "y",
    ]
    assert list(inspect.signature(ph.group_ocr_records).parameters) == [
        "records", "y_ratio",
    ]
    assert OCRLine.__module__ == "picture_capture.paddle_headwords_core"
    assert ph.OCRLine is OCRLine
    assert public_paddle.OCRLine is OCRLine


def test_column_classification_uses_full_intervals_gutters_and_curved_paths():
    geo = _geometry()
    for x, y, want in (
        (15, 10, 0), (130, 10, 1), (70, 10, 0),
        (100, 10, 1), (200, 20, 1), (125, 180, 0),
    ):
        assert pc.column_index_for_click(x, geo, y) == want
        assert reading_order.column_index_for_click(x, geo, y) == want
    assert pc.column_index_for_click(20, SimpleNamespace(
        column_starts=[], source_to_canonical=lambda x, y: (x, y)
    )) == 0


def test_sorting_and_stable_column_y_ties_match_leaf_with_real_entries():
    geo = _geometry()
    a = Entry(word="a", x=25, y=50)
    b = Entry(word="b", x=135, y=30)
    c = Entry(word="c", x=130, y=10)
    d = Entry(word="d", x=20, y=50)
    records = [b, a, c, d]
    expect_order = [d, a, c, b]
    assert pc.sort_entries_reading_order(records, geo) == expect_order
    assert reading_order.sort_entries_reading_order(records, geo) == expect_order
    assert pc.sort_entries_column_y(records, geo) == [a, d, c, b]
    assert pc.sort_entries_column_y(records, geo) == reading_order.sort_entries_column_y(records, geo)
    assert pc.entry_reading_order_key(a, geo) == reading_order.entry_reading_order_key(a, geo)


def test_reading_order_core_uses_live_facade_column_patch(monkeypatch):
    geo = _geometry()
    original = pc.column_index_for_click
    monkeypatch.setattr(public_processing, "column_index_for_click", lambda *args: 9)
    assert pc.entry_reading_order_key(Entry(word="word", x=15, y=30), geo)[1] == 9
    assert pc.sort_entries_column_y(
        [Entry(word="a", x=20, y=20), Entry(word="b", x=120, y=10)], geo,
    )[0].word == "b"
    monkeypatch.setattr(public_processing, "column_index_for_click", original)


def test_visual_line_group_and_logical_merge_keep_record_details():
    first = OCRRecord("casa", 0.9, (0, 0, 20, 10))
    second = OCRRecord("adj.", 0.8, (23, 1, 41, 11))
    distant = OCRRecord("body", 0.7, (0, 50, 20, 60))
    records = [second, distant, first, OCRRecord("", 0.1, (0, 0, 1, 1))]
    grouped = ph.group_ocr_records(records)
    assert grouped == line_grouping.group_ocr_records(records)
    assert [line.text for line in grouped] == ["casa adj.", "body"]
    assert all(type(line) is OCRLine for line in grouped)
    assert ph.group_ocr_records([]) == []
    grouped[0].logical_repairs = ("split", "join")
    grouped[1].logical_repairs = ("join", "wrap")
    merged = ph._merge_ocr_lines(grouped)
    assert merged == line_grouping.merge_ocr_lines(grouped)
    assert merged.logical_repairs == ("split", "join", "wrap")
    assert merged.records == [first, distant, second] or merged.records == [first, distant, second]


def test_ocr_line_grouping_reads_historical_public_overlap_patch(monkeypatch):
    records = [OCRRecord("first", 0.8, (0, 0, 10, 10)),
               OCRRecord("second", 0.6, (15, 100, 25, 110))]
    assert len(ph.group_ocr_records(records)) == 2
    original = ph._vertical_overlap
    monkeypatch.setattr(public_paddle, "_vertical_overlap", lambda *args: 1.0)
    assert len(ph.group_ocr_records(records)) == 1
    monkeypatch.setattr(public_paddle, "_vertical_overlap", original)
