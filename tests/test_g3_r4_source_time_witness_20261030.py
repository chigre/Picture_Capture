"""R4.2 provenance witness is recorded only after a successful PDIC commit.

These are synthetic fixtures: no scans, human verification or OCR accuracy claims.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import AppSettings, Entry
from picture_capture.proofreading.review_risk_witness_storage import (
    publish_review_risk_witnesses,
    load_review_risk_witness,
    review_risk_witness_path,
)
from picture_capture.proofreading.review_risk_queue import review_risk_from_files


def setup_files(tmp_path, *, duplicates=False):
    project = tmp_path / "project"
    project.mkdir(parents=True)
    page = project / "p001.png"
    page.write_bytes(b"synthetic image placeholder")
    cache = project / "QT" / "PaddleOCR" / "p001.json"
    cache.parent.mkdir(parents=True)
    pdic = project / "p001.pdic"
    row = {
        "candidate_id": "c1-y100", "word": "atlas", "source_x": 12, "source_y": 100,
        "coordinate_space": "source_image_pixels", "position_variant": "refined",
        "selected": True, "final_engine": "paddle",
        "decision_reason": "dual_agree_higher_quality",
        "needs_review": False, "issue_types": [],
        "paddle": {"accepted": True, "lemma": "atlas", "confidence": 0.97},
        "tesseract": {"accepted": True, "lemma": "atlas", "confidence": 0.96},
    }
    payload = {"signature": "synthetic", "review_candidates": [row]}
    if duplicates:
        payload["review_candidates"].append(dict(row))
    cache.write_text(json.dumps(payload), encoding="utf-8")
    return project, page, cache, pdic, row


def publish(project, page, cache, pdic):
    return publish_review_risk_witnesses(
        project_root=project, page=page, cache_path=cache, pdic_path=pdic,
    )


def risk(project, page, cache, pdic):
    witness = load_review_risk_witness(cache, "c1-y100")
    from picture_capture.persistence.project_storage import page_sections_read_path_for_image
    return review_risk_from_files(
        pdic_path=pdic, cache_path=cache, section_path=page_sections_read_path_for_image(page),
        witness=witness, project_key=str(project.resolve()), page_key=page.name,
        section_key="whole-page",
    )


def test_opt_in_default_is_off():
    assert AppSettings().focused_review_risk_witness_capture is False


def test_no_pdic_no_origin_witness_and_no_file_modification(tmp_path):
    project, page, cache, pdic, _ = setup_files(tmp_path)
    before = cache.read_bytes()
    assert publish(project, page, cache, pdic) == 0
    assert not review_risk_witness_path(cache).exists()
    assert cache.read_bytes() == before


def test_post_save_producer_captures_readback_and_exact_candidate(tmp_path):
    project, page, cache, pdic, row = setup_files(tmp_path)
    write_pdic(pdic, [Entry(word="atlas", x=12, y=100)], 300, ("p001","@","@"))
    before = [cache.read_bytes(), pdic.read_bytes()]
    assert publish(project, page, cache, pdic) == 1
    witness = load_review_risk_witness(cache, "c1-y100")
    assert witness is not None
    assert witness.cache_sha256 == hashlib.sha256(before[0]).hexdigest()
    assert witness.pdic_sha256 == hashlib.sha256(before[1]).hexdigest()
    assert risk(project, page, cache, pdic).tier == "normal"
    assert [cache.read_bytes(), pdic.read_bytes()] == before


def test_changed_cache_or_pdic_invalidates_source_witness(tmp_path):
    project, page, cache, pdic, row = setup_files(tmp_path)
    write_pdic(pdic, [Entry(word="atlas", x=12, y=100)], 300, ("p001","@","@"))
    assert publish(project, page, cache, pdic) == 1
    cache.write_bytes(cache.read_bytes() + b" ")
    assert load_review_risk_witness(cache, "c1-y100") is None
    assert risk(project, page, cache, pdic).tier == "unknown"


def test_manual_pdic_edit_invalidates_source_witness(tmp_path):
    project, page, cache, pdic, _ = setup_files(tmp_path)
    write_pdic(pdic, [Entry(word="atlas", x=12, y=100)], 300, ("p001","@","@"))
    assert publish(project, page, cache, pdic) == 1
    write_pdic(pdic, [Entry(word="atlas edited", x=12, y=100)], 300, ("p001","@","@"))
    assert load_review_risk_witness(cache, "c1-y100") is None
    assert risk(project, page, cache, pdic).tier == "unknown"


def test_duplicate_ids_xy_or_word_mismatch_never_attested(tmp_path):
    project, page, cache, pdic, _ = setup_files(tmp_path, duplicates=True)
    write_pdic(pdic, [Entry(word="atlas", x=12, y=100)], 300, ("p001","@","@"))
    assert publish(project, page, cache, pdic) == 0
    assert load_review_risk_witness(cache, "c1-y100") is None
    project2, page2, cache2, pdic2, _ = setup_files(tmp_path / "second")
    write_pdic(pdic2, [Entry(word="different", x=12, y=100)], 300, ("p001","@","@"))
    assert publish(project2, page2, cache2, pdic2) == 0


def test_section_sidecar_fails_closed_until_source_geometry_attested(tmp_path):
    project, page, cache, pdic, _ = setup_files(tmp_path)
    write_pdic(pdic, [Entry(word="atlas", x=12, y=100)], 300, ("p001","@","@"))
    from picture_capture.persistence.project_storage import page_sections_path_for_image
    section = page_sections_path_for_image(page)
    section.parent.mkdir(parents=True, exist_ok=True)
    section.write_text('{"sections":[{"index":1}]}')
    assert publish(project, page, cache, pdic) == 0
    assert load_review_risk_witness(cache, "c1-y100") is None


def test_post_save_replacement_is_detected_and_no_new_origin_published(tmp_path, monkeypatch):
    project, page, cache, pdic, _ = setup_files(tmp_path)
    write_pdic(pdic, [Entry(word="atlas", x=12, y=100)], 300, ("p001","@","@"))
    from picture_capture.proofreading import review_risk_witness_storage as owner
    original = owner.write_text_atomic
    def concurrent_write(path, text):
        cache.write_bytes(cache.read_bytes() + b" ")
        return original(path, text)
    monkeypatch.setattr(owner, "write_text_atomic", concurrent_write)
    with pytest.raises(RuntimeError, match="(changed|changed during|source)"):
        publish(project, page, cache, pdic)
    assert load_review_risk_witness(cache, "c1-y100") is None


def test_malformed_or_replaced_witness_never_loads(tmp_path):
    project, page, cache, pdic, _ = setup_files(tmp_path)
    write_pdic(pdic, [Entry(word="atlas", x=12, y=100)], 300, ("p001","@","@"))
    assert publish(project, page, cache, pdic) == 1
    sidecar = review_risk_witness_path(cache)
    sidecar.write_text('{"format":"other","witnesses":[]}')
    assert load_review_risk_witness(cache, "c1-y100") is None
