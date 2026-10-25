"""Issue #562 round 13: latent review signal and source pixel column offset leaves."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from picture_capture import processing as public_processing
from picture_capture import processing_core as core
from picture_capture.geometry import column_offsets
from picture_capture.ordinary import review_signals

PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_leaf_inventory_original_functions_and_exact_signatures():
    assert len(list(PKG.glob("*.py"))) == 9
    for path in ("geometry/column_offsets.py", "ordinary/review_signals.py"):
        assert (PKG / path).is_file()
        assert not (PKG / Path(path).name).exists()
    for fn in (
        core._column_start_offsets_canonical, core.apply_column_start_offsets,
        core._review_candidate_has_strong_positive_visual,
        core._review_candidate_hard_negative_level,
        core._review_candidate_hard_negative_consensus,
        core._latent_review_rows,
    ):
        assert fn.__module__ == "picture_capture.processing_core"
    assert list(inspect.signature(core.apply_column_start_offsets).parameters) == [
        "base_starts", "offsets", "gutter", "max_x",
    ]
    assert list(inspect.signature(core._latent_review_rows).parameters) == [
        "review_candidates", "geometry",
    ]


def test_column_offsets_are_literal_and_never_cross(monkeypatch):
    settings = SimpleNamespace(column_start_offsets=[-2.5, "broken", 15.2])
    assert core._column_start_offsets_canonical(settings, 4, 500) == [-2, 0, 15, 0]
    old = core._source_px
    monkeypatch.setattr(public_processing, "_source_px", lambda v: 7)
    assert core._column_start_offsets_canonical(settings, 2, 500) == [7, 7]
    monkeypatch.setattr(public_processing, "_source_px", old)
    assert column_offsets.column_start_offsets_canonical(
        settings, 4, 500, source_px_fn=old,
    ) == [-2, 0, 15, 0]
    assert core.apply_column_start_offsets([], [], gutter=10, max_x=200) == []
    adjusted = core.apply_column_start_offsets(
        [10, 90, 170], [0, -999, 0], gutter=10, max_x=240,
    )
    assert adjusted == column_offsets.apply_column_start_offsets(
        [10, 90, 170], [0, -999, 0], gutter=10, max_x=240,
    )
    assert adjusted == sorted(adjusted)
    assert all(0 <= x <= 240 for x in adjusted)


def _dual_candidate():
    return {
        "position_variant": "refined",
        "paddle": {
            "y": 20, "confidence": .95, "reason": "continuation_fragment",
            "features": {"looks_like_continuation": True},
        },
        "tesseract": {
            "y": 21, "confidence": .9, "reason": "internal_relation_label",
            "features": {"internal_relation_label": True},
        },
    }


def test_hard_negative_dual_single_and_visual_veto(monkeypatch):
    c = _dual_candidate()
    assert core._review_candidate_hard_negative_level(c) == "dual"
    assert core._review_candidate_hard_negative_consensus(c)
    assert review_signals.hard_negative_level(
        c, positive_fn=core._review_candidate_has_strong_positive_visual,
        hard_reasons=core._COMBINED_HARD_NEGATIVE_REASONS,
    ) == "dual"
    single = _dual_candidate()
    single["tesseract"]["confidence"] = 0.1
    assert core._review_candidate_hard_negative_level(single) == "single"
    single["paddle"]["confidence"] = 0.89
    assert core._review_candidate_hard_negative_level(single) == ""
    c["paddle"]["features"]["visual_entry_marker"] = True
    assert core._review_candidate_hard_negative_level(c) == ""
    c["paddle"]["features"]["visual_entry_marker"] = False
    old = core._review_candidate_has_strong_positive_visual
    monkeypatch.setattr(
        public_processing, "_review_candidate_has_strong_positive_visual",
        lambda candidate: True,
    )
    assert core._review_candidate_hard_negative_level(c) == ""
    monkeypatch.setattr(
        public_processing, "_review_candidate_has_strong_positive_visual", old,
    )
    assert core._review_candidate_hard_negative_level(c) == "dual"


def test_latent_review_rows_use_current_column_classifier(monkeypatch):
    geo = SimpleNamespace(source_to_canonical=lambda x, y: (x, y + 17))
    rows = [
        {"source_x": "4", "source_y": "25", "position_variant": "refined"},
        {"source_x": 5, "source_y": 0},
        {"source_x": 9, "source_y": 35, "selected": True},
        {"source_x": 12, "source_y": 31, "position_variant": "original"},
        {"source_x": "broken", "source_y": 20},
    ]
    original = core.column_index_for_click
    calls = []
    def column(x, geometry, y):
        calls.append((x, y))
        return 2
    monkeypatch.setattr(public_processing, "column_index_for_click", column)
    got = core._latent_review_rows(rows, geo)
    assert len(got) == 1
    assert got[0][0] is rows[0]
    assert got[0][1:] == (2, 42)
    assert calls == [(4, 25)]
    assert got == review_signals.latent_review_rows(rows, geo, column_fn=column)
    monkeypatch.setattr(public_processing, "column_index_for_click", original)
