"""B2 privacy-safe event audits and stale/fingerprint regression checks."""
from __future__ import annotations

import hashlib
import json

import pytest

from picture_capture.proofreading_events import append_event, make_event, sha256_file
from picture_capture.proofreading_evidence import link_event_to_final
from picture_capture.proofreading_quality_export import (
    EXPORT_FORMAT, summarize_local_events,
)


def _build(tmp_path):
    pdic = tmp_path / "page.PDIC"
    pdic.write_text("highly confidential lemma", encoding="utf-8")
    scan = tmp_path / "private_dictionary_image.png"
    scan.write_bytes(b"image content private")
    journal = tmp_path / "evidence.json"
    return pdic, scan, journal


def test_export_is_aggregate_only_and_requires_license(tmp_path):
    pdic, image, journal = _build(tmp_path)
    item = make_event(
        page_id="internal-private-page", action="rename",
        before={"word": "highly confidential lemma", "x": 10, "y": 100},
        after={"word": "corrected confidential lemma", "x": 10, "y": 100},
        pdic_sha256=sha256_file(pdic),
        image_sha256=sha256_file(image),
    )
    append_event(journal, item, pdic_file=pdic)
    output = summarize_local_events(
        journal, pdic, image_path=image,
        project_id="stable-project-1",
        license_statement="Internal use only; not licensed for training",
    )
    assert output["format"] == EXPORT_FORMAT
    assert output["change_types"] == {"text_only": 1}
    assert output["dataset_source_sha256"] == hashlib.sha256(journal.read_bytes()).hexdigest()
    assert output["verified_positive_labels"] == 0
    assert output["training_labels_exported"] == 0
    assert "private" not in json.dumps(output, ensure_ascii=False)
    assert "confidential lemma" not in json.dumps(output, ensure_ascii=False)
    assert output["license_statement"] == "Internal use only; not licensed for training"
    with pytest.raises(ValueError, match="license"):
        summarize_local_events(
            journal, pdic, project_id="stable-project-1", license_statement=""
        )


def test_export_reports_prior_event_staleness_after_manual_changes(tmp_path):
    pdic, image, journal = _build(tmp_path)
    item = make_event(
        page_id="p1", action="delete", before={"word": "secret", "x": 1, "y": 2},
        after=None, pdic_sha256=sha256_file(pdic), image_sha256=sha256_file(image),
    )
    append_event(journal, item, pdic_file=pdic)
    pdic.write_text("new hand correction", encoding="utf-8")
    result = summarize_local_events(
        journal, pdic, image_path=image,
        project_id="stable-project-1", license_statement="Not licensed",
    )
    assert result["provenance"]["stale_events"] == 1
    assert result["change_types"]["delete"] == 1
    assert result["training_labels_exported"] == 0


def test_missing_source_images_are_not_claimed_as_verified(tmp_path):
    pdic, image, journal = _build(tmp_path)
    item = make_event(
        page_id="p1", action="delete", before={"word": "old"}, after=None,
        pdic_sha256=sha256_file(pdic), image_sha256=sha256_file(image),
    )
    append_event(journal, item, pdic_file=pdic)
    result = summarize_local_events(
        journal, pdic, image_path=None,
        project_id="p", license_statement="unknown rights",
    )
    assert result["provenance"]["stale_events"] == 1


def test_candidate_without_full_source_fingerprints_is_unknown():
    event = {
        "operation_id": "op1", "candidate_id": "cand-a",
        "verification_status": "verified", "pdic_sha256": "a" * 64,
        "ocr_signature": None, "final_snapshot_sha256": None,
    }
    source = {
        "format": "picture-capture-final-ocr-decisions-v1",
        "ocr_cache_signature": "v1", "pdic_snapshot_sha256": "s1",
        "candidate_decisions": [{"candidate_id": "cand-a", "final_status": "retained"}],
    }
    result = link_event_to_final(event, source, current_ocr_signature="v1")
    assert result["status"] == "unknown"
    assert result["reason"] == "missing_provenance_fingerprint"
    assert result["training_label"] is None


def test_explicit_export_cli_does_not_overwrite_source_or_pdic():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "scripts" / "export_proofreading_quality.py").read_text(encoding="utf-8")
    assert "parser.add_argument(\"--output\"" in src
    assert "args.pdic.resolve()" in src
    assert "args.journal.resolve()" in src
    assert "args.image.resolve()" in src
    assert "args.output.exists()" in src
    assert "write_text_atomic(" in src
