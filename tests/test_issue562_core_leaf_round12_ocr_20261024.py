"""Issue #562: logical OCR line repair remains patchable and preserves Y."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
import re

from picture_capture import paddle_headwords as public_paddle
from picture_capture import paddle_headwords_core as core
from picture_capture.ocr import line_structure_repairs
from picture_capture.ocr.headword_models import OCRLine, OCRRecord

PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def make_line(text, box):
    return OCRLine(text, 0.9, box, [OCRRecord(text, 0.9, box)])


def settings():
    return SimpleNamespace(paddle_pos_search_chars=72)


def patterns():
    return (re.compile(".*"), re.compile(".*"), re.compile(r"s\.f\.|adj\."))


def parsed(text, *_args):
    return SimpleNamespace(
        normalized="agroalimentacion" if "agroalimentacion" in text else "casa",
        has_pos=("adj." in text or "s.f." in text),
        has_inflection=False,
        has_descriptor=False,
        looks_like_continuation=False,
    )


def find_pos(text, regex, max_chars):
    return re.search(r"s\.f\.|adj\.", text[:max_chars]), False


def test_historical_core_signatures_class_identity_and_leaf_presence():
    assert len(list(PKG.glob("*.py"))) == 7
    assert (PKG / "ocr/line_structure_repairs.py").is_file()
    assert not (PKG / "line_structure_repairs.py").exists()
    for fn in (
        core._repair_split_headword_lines,
        core._repair_wrapped_headword_structure,
        core._repair_multiline_headword_state_machine,
    ):
        assert fn.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(core._repair_multiline_headword_state_machine).parameters) == [
        "lines", "settings", "left_limit", "patterns", "max_follow_lines",
    ]
    assert core.OCRLine is OCRLine
    assert OCRLine.__module__ == "picture_capture.paddle_headwords_core"


def test_same_row_split_repair_uses_current_parser_and_line_merger(monkeypatch):
    first = make_line("casa", (5, 10, 38, 20))
    second = make_line("adj.", (42, 10, 68, 20))
    old = core.parse_headword_text
    monkeypatch.setattr(public_paddle, "parse_headword_text", parsed)
    actual = core._repair_split_headword_lines([first, second], settings(), 12, patterns())
    assert any("RIGHT_FRAGMENT_ABSORBED" in l.logical_repairs for l in actual)
    assert any(l.text.startswith("casa") and "adj." in l.text for l in actual)
    assert first.box == (5, 10, 38, 20)
    monkeypatch.setattr(public_paddle, "parse_headword_text", old)


def test_wrapped_pos_repair_anchors_text_to_first_physical_line():
    first = make_line("agroalimentacion (pl.)", (5, 10, 90, 20))
    next_line = make_line("s.f. genus", (5, 24, 63, 34))
    out = line_structure_repairs.repair_wrapped_headword_structure(
        [first, next_line], settings(), 12, patterns(),
        parse_fn=lambda text, *_: SimpleNamespace(
            has_pos=False, looks_like_continuation=False,
        ),
        find_pos_fn=find_pos, strip_fn=lambda prefix: "",
    )
    assert out[0].box == first.box
    assert out[0].text.endswith("s.f.")
    assert out[0].logical_repairs == ("MULTILINE_POS",)
    assert out[1] is next_line


def test_multiline_state_machine_does_not_shift_anchor_y():
    first = make_line("agroalimentacion (", (5, 10, 90, 20))
    next_line = make_line("s.f.)", (15, 25, 50, 35))
    out = line_structure_repairs.repair_multiline_headword_state_machine(
        [first, next_line], settings(), 12, patterns(),
        parse_fn=parsed, find_pos_fn=find_pos,
    )
    assert out[0].box == first.box
    assert out[0].text == "agroalimentacion ( s.f.)"
    assert "MULTILINE_STATE_JOIN:1" in out[0].logical_repairs
    assert out[0].records[0] is first.records[0]
    assert out[0].records[1] is next_line.records[0]


def test_core_live_parser_patch_blocks_or_enables_repair(monkeypatch):
    first, second = (
        make_line("casa", (5, 10, 38, 20)),
        make_line("adj.", (42, 10, 68, 20)),
    )
    original = core.parse_headword_text
    monkeypatch.setattr(public_paddle, "parse_headword_text", lambda *_: SimpleNamespace(
        has_pos=False, has_inflection=False, has_descriptor=False,
    ))
    out = core._repair_split_headword_lines([first, second], settings(), 12, patterns())
    assert out[0] is first
    monkeypatch.setattr(public_paddle, "parse_headword_text", original)
