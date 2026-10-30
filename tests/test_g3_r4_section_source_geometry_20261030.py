"""R4.2 SECTION-to-source XY mapping: never guess the nearest SECTION.

Synthetic PIL pixels / saved SECTION v2 only; no real scan or human verification.
"""
from __future__ import annotations

import hashlib
import json

import pytest
from PIL import Image

from picture_capture.geometry.layout_transform import LayoutTransform
from picture_capture.io.formats import write_pdic
from picture_capture.models import Entry
from picture_capture.persistence.page_sections import PageSection, write_page_sections
from picture_capture.persistence.project_storage import page_sections_read_path_for_image
from picture_capture.proofreading.review_section_provenance import (
    section_key_for_source_point,
)
from picture_capture.proofreading.review_risk_witness_storage import (
    load_review_risk_witness, publish_review_risk_witnesses,
)
from picture_capture.proofreading.review_risk_queue import review_risk_from_files


def _fixture(tmp_path, transform="identity"):
    project = tmp_path / "project"
    project.mkdir()
    page = project / "001.png"
    Image.new("RGB", (200, 300), "white").save(page)
    cache = project / "QT" / "PaddleOCR" / "001.json"
    cache.parent.mkdir(parents=True)
    pdic = project / "001.pdic"
    kind = LayoutTransform(transform)
    src_xy = kind.canonical_to_source_point(40, 45, (200, 300))
    x, y = src_xy
    candidate = {
        "candidate_id": "sec-candidate", "word": "atlas",
        "source_x": x, "source_y": y, "selected": True,
        "coordinate_space": "source_image_pixels", "position_variant": "refined",
        "final_engine": "paddle", "decision_reason": "dual_agree_higher_quality",
        "needs_review": False, "issue_types": [],
        "paddle": {"accepted": True, "lemma": "atlas", "confidence": .95},
        "tesseract": {"accepted": True, "lemma": "atlas", "confidence": .96},
    }
    cache.write_text(json.dumps({"signature": "synthetic", "review_candidates": [candidate]}), encoding="utf-8")
    write_pdic(pdic, [Entry(word="atlas", x=x, y=y)], 200, ("001", "@", "@"))
    section = write_page_sections(page, [PageSection(20, 90), PageSection(120, 180)], layout_transform=transform)
    return project, page, cache, pdic, section, candidate


@pytest.mark.parametrize("transform", ["identity", "mirror_x", "rotate_ccw90", "rotate_cw90"])
def test_strict_source_xy_maps_to_correct_section_under_every_layout_transform(tmp_path, transform):
    project, page, cache, pdic, section, row = _fixture(tmp_path, transform)
    x, y = row["source_x"], row["source_y"]
    assert section_key_for_source_point(page, section, x, y) == "section-1"
    kind = LayoutTransform(transform)
    x2, y2 = kind.canonical_to_source_point(40, 140, (200, 300))
    assert section_key_for_source_point(page, section, x2, y2) == "section-2"
    gap = kind.canonical_to_source_point(40, 105, (200, 300))
    assert section_key_for_source_point(page, section, *gap) is None
    assert section_key_for_source_point(page, section, -1, y) is None
    assert section_key_for_source_point(page, section, 200, y) is None


@pytest.mark.parametrize("mutation", [
    lambda p: p.update({"source_width": 300}),
    lambda p: p.update({"coordinate_space": "canonical_image_pixels"}),
    lambda p: p.update({"format": "unknown"}),
    lambda p: p["sections"][0].update({"index": 2}),
    lambda p: p["sections"][0].update({"bottom_source_segment_xyxy": [[0, 200], [199, 200]]}),
    lambda p: p["sections"].append(dict(p["sections"][0], index=3)),
    lambda p: p.update({"sections": [{"index": 1}]}),
])
def test_malformed_stale_overlapping_or_partial_section_data_never_maps(tmp_path, mutation):
    *_, page, cache, pdic, section, row = (None, *_fixture(tmp_path))
    payload = json.loads(section.read_text("utf-8"))
    mutation(payload)
    section.write_text(json.dumps(payload), encoding="utf-8")
    assert section_key_for_source_point(page, section, row["source_x"], row["source_y"]) is None


@pytest.mark.parametrize("transform", ["identity", "mirror_x", "rotate_ccw90", "rotate_cw90"])
def test_source_time_section_witness_readback_and_classification(tmp_path, transform):
    project, page, cache, pdic, section, row = _fixture(tmp_path, transform)
    old = [cache.read_bytes(), pdic.read_bytes(), section.read_bytes(), page.read_bytes()]
    assert publish_review_risk_witnesses(
        project_root=project, page=page, cache_path=cache, pdic_path=pdic
    ) == 1
    witness = load_review_risk_witness(cache, "sec-candidate")
    assert witness is not None
    assert witness.section_key == "section-1"
    assert witness.section_sha256 == hashlib.sha256(old[2]).hexdigest()
    assert [cache.read_bytes(), pdic.read_bytes(), section.read_bytes(), page.read_bytes()] == old
    result = review_risk_from_files(
        pdic_path=pdic, cache_path=cache, section_path=section,
        witness=witness, project_key=str(project.resolve()),
        page_key=page.name, section_key="section-1",
        section_at_source_xy=lambda x, y: section_key_for_source_point(page, section, x, y),
    )
    assert result.tier == "normal"


def test_corrupt_section_bytes_or_replaced_image_invalidates_witness(tmp_path):
    project, page, cache, pdic, section, row = _fixture(tmp_path)
    assert publish_review_risk_witnesses(
        project_root=project, page=page, cache_path=cache, pdic_path=pdic
    ) == 1
    section.write_bytes(section.read_bytes() + b" ")
    assert load_review_risk_witness(cache, "sec-candidate") is None
    # A new source image of identical dimensions must not resurrect an old
    # witness when section bytes are restored.
    project2, page2, cache2, pdic2, section2, row2 = _fixture(tmp_path / "second")
    assert publish_review_risk_witnesses(project_root=project2, page=page2, cache_path=cache2, pdic_path=pdic2) == 1
    Image.new("RGB", (200, 300), "black").save(page2)
    assert load_review_risk_witness(cache2, "sec-candidate") is None


def test_gap_source_xy_is_not_attested_by_nearest_section_fallback(tmp_path):
    project, page, cache, pdic, section, row = _fixture(tmp_path)
    row["source_y"] = 105
    cache.write_text(json.dumps({"review_candidates": [row]}))
    write_pdic(pdic, [Entry(word="atlas", x=row["source_x"], y=105)], 200, ("001", "@", "@"))
    assert publish_review_risk_witnesses(project_root=project, page=page, cache_path=cache, pdic_path=pdic) == 0
    assert load_review_risk_witness(cache, "sec-candidate") is None
