"""OCR text choices must represent distinct valid alternatives.

The 'single-line OCR drawing candidate' checkbox remains a separate
detection-review setting; this regression forbids substituting a disabled
checkbox on an already-saved PDIC entry. No patient/scan pixels needed.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.review_text_helpers import (
    _candidate_choice_rows, _has_distinct_ocr_alternatives,
)


@pytest.mark.parametrize(("candidate", "available"), [
    (None, False),
    ({}, False),
    ({"word": ""}, False),
    ({"word": "甲"}, False),
    ({"paddle": {"lemma": "甲"}, "word": "甲"}, False),
    ({"paddle": {"lemma": " 甲 "}, "word": "甲 "}, False),
    ({"paddle": {"lemma": "甲"}, "lens": {"lemma": "甲"}, "word": "甲"}, False),
    ({"paddle": {"lemma": ""}, "tesseract": {}, "word": "甲"}, False),
    ({"paddle": {"lemma": "甲"}, "tesseract": {"lemma": "乙"}, "word": "甲"}, True),
    ({"paddle": {"lemma": "甲"}, "lens": {"lemma": "乙"}, "word": "乙"}, True),
    ({"paddle": {"lemma": "甲"}, "word": "乙"}, False),
    ({"paddle": {"lemma": "甲"}, "tesseract": {"lemma": "甲"}, "word": "乙"}, False),
])
def test_choices_really_have_distinct_nonempty_text(candidate, available):
    assert _has_distinct_ocr_alternatives(candidate) is available


def test_duplicate_fusion_result_is_retained_only_when_other_real_choice_exists():
    candidate = {
        "paddle": {"lemma": "甲", "confidence": 0.93},
        "tesseract": {"lemma": "乙", "confidence": 0.71},
        "word": "甲",
    }
    assert _has_distinct_ocr_alternatives(candidate)
    rows = _candidate_choice_rows(candidate)
    assert [v[2] for v in rows] == ["甲", "乙", "甲"]
    assert rows[-1][-1] is True


def test_main_menu_guard_and_drawing_checkbox_semantics_are_separate():
    src = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    shell = (src / "app.py").read_text(encoding="utf-8")
    ui = (src / "ui" / "entry_overlay_builder.py").read_text(encoding="utf-8")
    menu_method = shell.split("    def _create_main_ocr_menu(", 1)[1].split(
        "\n    def _paddle_cache_path(", 1,
    )[0]
    assert "if not _has_distinct_ocr_alternatives(candidate) or not rows:" in menu_method
    assert 'tk.Checkbutton(' not in ui
    assert 'text="候选"' not in ui
    assert 'ocr_x = marker_right_screen_x' in ui
    assert 'ocr_anchor = "nw"' in ui
    assert 'paddle_show_candidate_checkboxes' not in ui
