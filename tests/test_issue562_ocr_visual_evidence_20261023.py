"""#562 full OCR visual marker and CJK image-evidence owner boundary."""
from __future__ import annotations

from dataclasses import fields
import subprocess
import sys

import numpy as np
import pytest

from picture_capture import paddle_headwords_core as core
from picture_capture.ocr import visual_evidence as owner
from picture_capture.models import AppSettings


def test_visual_owner_leaf_import_excludes_core_gui_and_native_ocr():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.ocr.visual_evidence import VisualEvidenceDeps
assert 'picture_capture.paddle_headwords_core' not in sys.modules
assert 'picture_capture.paddle_headwords' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


def test_call_time_dependencies_preserve_original_private_patch_points():
    names = {field.name for field in fields(owner.VisualEvidenceDeps)}
    assert len(names) == 29
    assert {"_binary_rle_components", "_visual_family_symbol",
            "_cjk_visual_projection_runs", "_cjk_word_for_visual_run",
            "_SYMBOL_FAMILY_BY_LITERAL", "match_visual_marker_template"} <= names
    current = core._visual_evidence_deps()
    assert current._cjk_word_for_visual_run is core._cjk_word_for_visual_run
    assert current._SYMBOL_FAMILY_BY_LITERAL is core._SYMBOL_FAMILY_BY_LITERAL


def test_binary_connected_components_preserves_bbox_and_eight_neighborhood():
    mask = np.zeros((8, 12), dtype=bool)
    mask[1:3, 2:4] = True
    mask[3, 4] = True  # Diagonal 8-connected to first blob
    mask[5:7, 9:11] = True
    found = sorted(core._binary_rle_components(mask))
    assert found == [(2, 1, 5, 4, 5), (9, 5, 11, 7, 4)]
    assert core._binary_rle_components(np.empty((0, 3), dtype=bool)) == []


def test_visual_symbol_classification_rejects_zero_width_candidate():
    assert core._classify_visual_symbol_component(
        np.zeros((10, 0), dtype=bool), 12., {"visual_families": []}
    ) is None


def test_unicode_single_cjk_leading_token_guard_and_pinyin_behavior():
    assert core._leading_cjk_ideograph("案") == "案"
    assert core._leading_cjk_ideograph("案1") == "案"
    assert core._leading_cjk_ideograph("案 àn") == "案"
    assert core._leading_cjk_ideograph("案例") == ""
    assert core._leading_cjk_ideograph("非案") == ""
    assert core._leading_cjk_ideograph("") == ""


def test_visual_helper_uses_live_core_patch_instead_of_import_time_copy(monkeypatch):
    monkeypatch.setattr(core, "_is_single_cjk_ideograph", lambda glyph: False)
    assert core._leading_cjk_ideograph("案1") == ""


def test_configured_symbol_family_uses_live_mapping(monkeypatch):
    monkeypatch.setattr(core, "_SYMBOL_FAMILY_BY_LITERAL", {"◇": "diamond"})
    found = core._visual_family_symbol(
        {"entry_markers": ["◇"], "bracket_openers": []}, "diamond")
    assert found == ("◇", "entry_marker")
    assert core._visual_family_symbol(
        {"entry_markers": ["○"], "bracket_openers": []}, "diamond") is None


def test_right_context_features_keep_existing_json_field_prefixes():
    assert core._cjk_right_context_features(None) == {}
    assert core._cjk_candidate_right_context_features(None) == {}
    metrics = {
        "available": True, "sparse": True, "blank_ratio": .75,
        "lower_blank_ratio": .8, "row_occupancy": .1,
        "density_ratio": .2, "sparse_votes": 3,
    }
    broad = core._cjk_right_context_features(metrics)
    local = core._cjk_candidate_right_context_features(metrics)
    assert broad["cjk_right_context_available"] is True
    assert broad["cjk_right_context_sparse"] is True
    assert broad["cjk_right_blank_ratio"] == .75
    assert local["cjk_candidate_right_context_sparse"] is True
    assert local["cjk_candidate_right_blank_ratio"] == .75
    assert local["cjk_candidate_right_sparse_votes"] == 3


def test_empty_cjk_projection_and_unmatched_visual_run_are_noops():
    assert core._cjk_visual_projection_runs(
        np.empty((0, 30), dtype=np.uint8), 0, AppSettings(), 1.
    ) == (0, [])
    word, confidence, record = core._cjk_word_for_visual_run(
        [], (10, 50), 40, AppSettings())
    assert word == "" and confidence == 0. and record is None


def test_empty_visual_marker_alignment_does_not_invent_ocr_evidence():
    assert core._match_visual_entry_markers_to_lines([], [], 14.) == {}
    assert core._apply_trusted_visual_marker_lanes(
        [], None, template_threshold=.6) == []
