from __future__ import annotations

from types import SimpleNamespace

from picture_capture import app, review_text_helpers as review


def test_phase7e_app_reexports_review_text_helpers() -> None:
    for name in (
        "_review_editor_font_size",
        "_entry_font_spec",
        "_review_similarity_key",
        "_review_text_similarity",
        "_focused_review_character_tokens",
        "_focused_review_page_indices",
        "_focused_review_is_single_character",
        "_candidate_for_entry_from_list",
        "_candidate_word_for_ocr_source",
        "_review_similarity_color",
        "_candidate_choice_rows",
    ):
        assert getattr(app, name) is getattr(review, name)


def test_review_similarity_normalizes_width_case_and_punctuation() -> None:
    assert review._review_similarity_key("Ａ， B!") == "ab"
    assert review._review_text_similarity("Résumé", "RÉSUMÉ") == 1.0
    assert review._review_text_similarity("", "alpha") is None


def test_focused_review_page_indices_keep_one_based_user_contract() -> None:
    assert review._focused_review_page_indices("1-2,4", 5) == [0, 1, 3]
    assert review._focused_review_page_indices("", 3) == [0, 1, 2]


def test_candidate_helpers_keep_nearest_match_and_engine_rows() -> None:
    entry = SimpleNamespace(candidate_id="", x=10, y=20)
    candidate = {
        "source_x": 12,
        "source_y": 21,
        "word": "alpha",
        "final_engine": "fusion",
        "paddle": {"lemma": "alpha", "confidence": 0.9},
        "tesseract": {"lemma": "alfa", "confidence": 0.7},
        "lens": {},
    }

    assert review._candidate_for_entry_from_list(
        entry, [candidate], y_tolerance=5
    ) is candidate
    assert review._candidate_word_for_ocr_source(candidate, "paddle") == "alpha"
    rows = review._candidate_choice_rows(candidate)
    assert [row[0] for row in rows] == ["paddle", "tesseract", "fusion"]
    assert rows[-1][-1] is True
