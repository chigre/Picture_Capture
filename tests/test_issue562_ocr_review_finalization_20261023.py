"""#562: selected OCR review finalization owns CJK dedup and export summary."""
from __future__ import annotations

import subprocess
import sys

import pytest

from picture_capture import paddle_headwords_core as core
from picture_capture.ocr import review_finalization as leaf
from picture_capture.models import Entry


def row(word, y, *, score=3., height=20., column=0, selected=True):
    return {
        "word": word, "column": column, "source_x": 7, "source_y": y,
        "_axis_u": 7, "_axis_v": y, "_coarse_axis_v": y,
        "box": (1, y - 8, 20, y + 12), "line_height_reference": height,
        "score": score, "confidence": .9, "selected": selected,
        "needs_review": False, "issue_types": [], "final_engine": "paddle",
        "paddle": {"y": y, "accepted": True, "box": (1, y - 8, 20, y + 12)},
    }


def test_leaf_import_has_no_heavy_core_gui_or_paddle_dependencies():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.ocr.review_finalization import ReviewFinalizationDeps
assert 'picture_capture.paddle_headwords_core' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


def test_live_core_callbacks_are_bound_to_one_canonical_owner(monkeypatch):
    sentinel = object()
    def spy(deps, item):
        assert deps._review_candidate_box_height is core._review_candidate_box_height
        return sentinel
    monkeypatch.setattr(leaf, "_review_candidate_priority", spy)
    assert core._review_candidate_priority({}) is sentinel


def test_exact_duplicate_single_cjk_keeps_upper_source_boundary():
    upper = row("播", 100, score=2., height=12.)
    lower = row("播", 106, score=9., height=12.)
    rows = [upper, lower]
    assert core._single_cjk_duplicate_pair(upper, lower)
    assert core._deduplicate_selected_cjk_review_candidates(rows) == 1
    keep = [x for x in rows if x["selected"]]
    assert len(keep) == 1 and keep[0] is lower
    assert lower["source_y"] == 100 and lower["_axis_v"] == 100
    assert "SINGLE_CJK_DUPLICATE_MERGED" in lower["issue_types"]
    assert upper["decision_reason"] == "near_y_duplicate_suppressed"


def test_ordinary_duplicate_keeps_lower_source_boundary_and_loser_unselected():
    upper = row("atlas", 100, score=9.)
    lower = row("atlas", 103, score=2.)
    assert core._deduplicate_selected_cjk_review_candidates([upper, lower]) == 1
    assert upper["selected"] and upper["source_y"] == 103
    assert not lower["selected"]
    assert "NEAR_Y_DUPLICATE_MERGED" in upper["issue_types"]


def test_far_apart_real_entries_remain_selected():
    upper = row("atlas", 100)
    lower = row("other", 150)
    assert core._deduplicate_selected_cjk_review_candidates([upper, lower]) == 0
    assert upper["selected"] and lower["selected"]


def test_multi_character_cjk_compounds_require_exact_word_and_same_region():
    a = row("【並肩】", 100)
    b = row("並肩", 103)
    c = row("並別", 103)
    assert core._review_candidates_same_cjk_compound(a, b)
    assert not core._review_candidates_same_cjk_compound(a, c)


def test_selected_review_rows_create_original_entry_type_and_oversized_flags():
    accepted = row("播", 123, height=12.)
    accepted["candidate_id"] = "c1-y120"
    accepted["line_height_reference"] = 12.
    accepted["box"] = (1, 110, 25, 150)
    accepted["paddle"]["features"] = {"cjk_oversized_recovery": True}
    unselected = row("ghost", 150, selected=False)
    entries = core._entries_from_review_candidates([unselected, accepted])
    assert len(entries) == 1 and isinstance(entries[0], Entry)
    assert entries[0].__class__.__module__ == "picture_capture.models"
    assert entries[0].word == "播" and entries[0].y == 123
    assert entries[0].ocr_single_cjk and entries[0].ocr_oversized_cjk
    assert entries[0].candidate_id == "c1-y120"


def test_quality_summary_file_is_atomic_and_replaces_one_page_row(tmp_path):
    cache = tmp_path / "001.ocr.json"
    initial = {"agreement": 0.6, "candidate_union": 2}
    core._update_project_quality_summary(cache, initial, [
        {"selected": True, "needs_review": False, "issue_types": ["OCR_REPAIR"]},
    ])
    target = tmp_path / "_quality_summary.tsv"
    first = target.read_text(encoding="utf-8")
    assert first.startswith(core._QUALITY_HEADER + "\n")
    assert "001" in first and "0.6000" in first
    core._update_project_quality_summary(
        cache, {"agreement": .95, "candidate_union": 3}, [
            {"selected": True, "needs_review": True, "issue_types": []},
        ])
    second = target.read_text(encoding="utf-8")
    assert second.count("\n") == 2
    assert "0.9500" in second and "0.6000" not in second


def test_quality_summary_uses_call_time_publisher(monkeypatch, tmp_path):
    published = []
    monkeypatch.setattr(core, "_atomic_write_text",
                        lambda path, text, **kw: published.append((path, text, kw)))
    core._update_project_quality_summary(tmp_path / "xyz.ocr.json", {}, [])
    assert len(published) == 1
    assert published[0][0].name == "_quality_summary.tsv"
    assert published[0][2] == {"encoding": "utf-8"}
