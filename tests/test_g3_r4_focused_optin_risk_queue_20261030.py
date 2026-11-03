"""R4.2 opted-in per-page verified priority view, no stale cache guessing.

Synthetic OCR and generated image only. No user scans or verified labels.
"""
from __future__ import annotations

from dataclasses import replace
import pytest
import json

from PIL import Image

from picture_capture.io.formats import write_pdic
from picture_capture.models import AppSettings, Entry
from picture_capture.persistence.page_sections import PageSection, write_page_sections
from picture_capture.proofreading.review_risk_witness_storage import (
    publish_review_risk_witnesses,
)
from picture_capture.proofreading.review_risk_snapshot import (
    prioritized_focused_page_targets,
)


def _page(tmp_path, *, section=False):
    project = tmp_path / "project"
    project.mkdir(parents=True)
    page = project / "001.png"
    Image.new("RGB", (200, 300), "white").save(page)
    cache = project / "QT" / "PaddleOCR" / "001.json"
    cache.parent.mkdir(parents=True)
    pdic = project / "001.pdic"
    coords = [(30, 35), (30, 45), (30, 135), (30, 145)] if section else [(30, 35), (30, 45), (30, 55), (30, 65)]
    rows = []
    for i, (x,y) in enumerate(coords):
        rows.append({
            "candidate_id": f"c{i}", "word": f"word{i}",
            "source_x": x, "source_y": y,
            "selected": True, "coordinate_space": "source_image_pixels",
            "position_variant": "refined", "final_engine": "paddle",
            "decision_reason": "dual_agree_higher_quality",
            "needs_review": i % 2 == 1, "issue_types": ["OCR_CONFLICT"] if i%2 else [],
            "paddle": {"accepted": True, "lemma": f"word{i}", "confidence": .98},
            "tesseract": {"accepted": True, "lemma": f"word{i}", "confidence": .98},
        })
    cache.write_text(json.dumps({"signature":"synthetic","review_candidates": rows}))
    write_pdic(pdic, [Entry(word=f"word{i}", x=x,y=y) for i,(x,y) in enumerate(coords)], 200, ("001","@","@"))
    if section:
        write_page_sections(page, [PageSection(20, 90), PageSection(120, 180)])
    targets = [{"page_index":0, "page_name":"001.png", "x":x,"y":y,
                "original_word": f"word{i}", "current_word":f"word{i}",
                "reasons":("原筛选原因",)} for i,(x,y) in enumerate(coords)]
    return project,page,cache,pdic,targets


def _run(f, *, enabled=True):
    project,page,cache,pdic,targets = f
    return prioritized_focused_page_targets(
        targets, project_root=project, page=page,
        cache_path=cache, pdic_path=pdic, enabled=enabled,
    )


def test_opt_in_is_strictly_false_for_legacy_settings():
    assert AppSettings().focused_review_risk_queue_enabled is False


def test_disabled_returns_original_references_without_source_witness(tmp_path):
    f=_page(tmp_path)
    original=list(f[-1])
    result=_run(f,enabled=False)
    assert result == original
    assert all(x is y for x,y in zip(result,original))
    assert all("review_risk_tier" not in x for x in original)


def test_opted_in_without_proven_witness_never_reorders(tmp_path):
    f=_page(tmp_path)
    result=_run(f)
    assert result == f[-1]
    assert all(x["x"]==y["x"] and x["y"]==y["y"] for x,y in zip(result,f[-1]))


def test_verified_page_risks_sort_only_within_original_page_section(tmp_path):
    f=_page(tmp_path,section=True)
    project,page,cache,pdic,targets=f
    assert publish_review_risk_witnesses(
        project_root=project,page=page,cache_path=cache,pdic_path=pdic
    ) == 4
    before=[dict(row) for row in targets]
    result=_run(f)
    assert [row["original_word"] for row in result] == [
        "word1","word0","word3","word2"]
    assert [row["review_risk_tier"] for row in result] == [
        "priority","normal","priority","normal"]
    assert [row["section_key"] for row in result] == [
        "section-1","section-1","section-2","section-2"]
    assert targets == before


def test_original_order_is_restored_by_explicit_off_even_when_witness_exists(tmp_path):
    f=_page(tmp_path)
    project,page,cache,pdic,targets=f
    assert publish_review_risk_witnesses(project_root=project,page=page,cache_path=cache,pdic_path=pdic)==4
    result=_run(f,enabled=False)
    assert result == targets
    assert all(x is y for x,y in zip(result,targets))
    assert [x["original_word"] for x in _run(f)]==["word1","word3","word0","word2"]


def test_manual_pdic_edit_or_replaced_image_fails_closed(tmp_path):
    f=_page(tmp_path)
    project,page,cache,pdic,targets=f
    assert publish_review_risk_witnesses(project_root=project,page=page,cache_path=cache,pdic_path=pdic)==4
    pdic.write_bytes(pdic.read_bytes()+b" ")
    assert _run(f)==targets
    Image.new("RGB",(200,300),"black").save(page)
    assert _run(f)==targets


def test_ambiguous_target_or_sectionless_unknown_remains_not_a_safe_normal(tmp_path):
    f=_page(tmp_path)
    project,page,cache,pdic,targets=f
    assert publish_review_risk_witnesses(project_root=project,page=page,cache_path=cache,pdic_path=pdic)==4
    targets[0]["original_word"]="manually changed"
    result=_run(f)
    assert result[0]["original_word"]=="word1"
    assert next(x for x in result if x["original_word"]=="manually changed")["review_risk_tier"]=="unknown"


def test_same_source_point_unwitnessed_unknown_is_never_priority(tmp_path):
    f=_page(tmp_path)
    project,page,cache,pdic,targets=f
    assert publish_review_risk_witnesses(project_root=project,page=page,cache_path=cache,pdic_path=pdic)==4
    targets[2]["x"]=999
    result=_run(f)
    assert next(x for x in result if x["x"]==999)["review_risk_tier"]=="unknown"


def test_no_section_geometry_for_unknown_section_target_blocks_all_reordering(tmp_path):
    f=_page(tmp_path,section=True)
    project,page,cache,pdic,targets=f
    assert publish_review_risk_witnesses(project_root=project,page=page,cache_path=cache,pdic_path=pdic)==4
    targets[0]["x"]=999
    assert _run(f)==targets


def test_view_integration_is_off_without_intent_and_uses_existing_worker_epoch():
    from pathlib import Path
    base=Path(__file__).resolve().parents[1]/"src/picture_capture"
    scan=(base/"ui/focused_filter_workflow.py").read_text("utf-8")
    initializer=(base/"ui/review_window_initialization.py").read_text("utf-8")
    layout=(base/"ui/review_workspace_workflow.py").read_text("utf-8")
    assert "focused_review_risk_queue_enabled" in scan
    assert "focused_review_risk_queue_enabled" in initializer
    assert "focused_risk_priority_var" in scan
    assert "focused_risk_priority_var" in layout
    assert "prioritized_focused_page_targets" in scan
    assert "_filter_scan_serial" in scan
    assert "if serial != self._filter_scan_serial" in scan


@pytest.mark.parametrize(
    ("coordinate", "malformed"),
    [
        ("x", "30"), ("y", "35"),
        ("x", 30.0), ("y", 35.0),
        ("x", 30.7), ("y", 35.7),
        ("x", True), ("y", False),
        ("x", 1.0), ("y", 1.0),
    ],
)
def test_malformed_review_source_xy_never_inherits_ranked_witness(
    tmp_path, coordinate, malformed,
):
    """Fail closed without guessing or reordering the source page identity.

    The witness, PDIC, image and OCR candidate are independently synthetic and
    genuinely attested.  Only the *view target* source pixel type is invalid.
    A float/bool/text coordinate cannot become an integer source marker by
    coercion; even other valid rows cannot be ranked in the resulting mixed
    invalid queue, because that would hide the malformed target's owner.
    """
    fixture = _page(tmp_path)
    project, page, cache, pdic, targets = fixture
    assert publish_review_risk_witnesses(
        project_root=project, page=page, cache_path=cache, pdic_path=pdic,
    ) == 4
    targets[0][coordinate] = malformed
    before = list(targets)
    result = _run(fixture, enabled=True)
    assert result == before
    assert all(actual is original for actual, original in zip(result, before))
    assert all("review_risk_tier" not in row for row in result)


def test_exact_integer_review_source_xy_still_uses_verified_priority(tmp_path):
    """Positive control: retain existing stable opt-in behavior for true ints."""
    fixture = _page(tmp_path)
    project, page, cache, pdic, targets = fixture
    assert publish_review_risk_witnesses(
        project_root=project, page=page, cache_path=cache, pdic_path=pdic,
    ) == 4
    assert all(type(t["x"]) is int and type(t["y"]) is int for t in targets)
    result = _run(fixture, enabled=True)
    assert [row["original_word"] for row in result] == [
        "word1", "word3", "word0", "word2",
    ]
    assert [row["review_risk_tier"] for row in result] == [
        "priority", "priority", "normal", "normal",
    ]
    assert all("review_risk_tier" not in row for row in targets)


@pytest.mark.parametrize(("field", "invalid"), [
    ("page_index", 0.0),
    ("page_index", "0"),
    ("page_index", False),
    ("page_index", True),
    ("page_index", 1),
    ("page_name", "002.png"),
    ("page_name", ""),
    ("page_name", None),
    ("page_stem", "002"),
])
def test_optin_risk_source_page_owner_does_not_inherit_other_page_witness(
    tmp_path, field, invalid,
):
    """An attested *page* cannot rank a foreign or nonintegral view row.

    Real scans construct page_index, page_name and page_stem together. Here
    only the displayed target metadata is corrupted after software-owned
    synthetic OCR/PDIC origin publication; no real project files are used.
    """
    fixture = _page(tmp_path)
    project, page, cache, pdic, targets = fixture
    assert publish_review_risk_witnesses(
        project_root=project, page=page, cache_path=cache, pdic_path=pdic,
    ) == 4
    targets[0][field] = invalid
    before = [dict(row) for row in targets]
    result = _run(fixture, enabled=True)
    assert result == targets
    assert all(actual is original for actual, original in zip(result, targets))
    assert targets == before
    assert all("review_risk_tier" not in row for row in result)
    assert all("review_risk_reasons" not in row for row in result)


def test_verified_page_owner_still_opted_in_and_default_remains_off(tmp_path):
    fixture = _page(tmp_path)
    project, page, cache, pdic, targets = fixture
    assert publish_review_risk_witnesses(
        project_root=project, page=page, cache_path=cache, pdic_path=pdic,
    ) == 4
    assert [row["original_word"] for row in _run(fixture, enabled=True)] == [
        "word1", "word3", "word0", "word2",
    ]
    assert all(row["page_index"] == 0 for row in targets)
    assert all(row["page_name"] == page.name for row in targets)
    assert all("review_risk_tier" not in row for row in _run(fixture, enabled=False))
