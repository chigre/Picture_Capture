"""B2 explicit human judgment is user-invoked, image-bound and not training."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from picture_capture.proofreading_events import (
    append_event, load_events, make_event, sha256_file,
)
from picture_capture.proofreading_verification import (
    explicit_verification_counts, verify_saved_action,
)
from picture_capture.proofreading_quality_export import summarize_local_events


def _source(tmp_path, *, ocr_signature=None):
    pdic = tmp_path / "page.pdic"
    image = tmp_path / "page.png"
    journal = tmp_path / "events.json"
    pdic.write_bytes(b"saved human PDIC")
    image.write_bytes(b"original scanned image")
    event = make_event(
        page_id="p/page.png", action="rename",
        before={"word": "old", "x": 10, "y": 20},
        after={"word": "new", "x": 10, "y": 20},
        entry_id="stable-row-1",
        candidate_id="candidate-x" if ocr_signature else None,
        image_sha256=sha256_file(image),
        pdic_sha256=sha256_file(pdic),
        ocr_signature=ocr_signature,
        final_snapshot_sha256=("a" * 64) if ocr_signature else None,
    )
    append_event(journal, event, pdic_file=pdic)
    return pdic, image, journal, event


def _verify(pdic, image, journal, event, **kwargs):
    return verify_saved_action(
        journal=journal, pdic_file=pdic, image_file=image,
        operation_id=event["operation_id"], judgment="correct_headword",
        explicitly_confirmed=True, **kwargs,
    )


def test_visual_review_requires_explicit_confirmation_and_valid_judgment(tmp_path):
    pdic, image, journal, event = _source(tmp_path)
    with pytest.raises(ValueError, match="Explicit"):
        verify_saved_action(
            journal=journal, pdic_file=pdic, image_file=image,
            operation_id=event["operation_id"], judgment="correct_headword",
            explicitly_confirmed=False,
        )
    with pytest.raises(ValueError, match="Judgment"):
        verify_saved_action(
            journal=journal, pdic_file=pdic, image_file=image,
            operation_id=event["operation_id"], judgment="uncertain",
            explicitly_confirmed=True,
        )
    assert len(load_events(journal)) == 1


def test_positive_judgment_is_local_and_explicit_only(tmp_path):
    pdic, image, journal, event = _source(tmp_path)
    saved_pdic = pdic.read_bytes()
    saved_image = image.read_bytes()
    verification = _verify(pdic, image, journal, event)
    assert verification["action"] == "verify"
    assert verification["verification_status"] == "verified"
    assert verification["after"] == {"judgment": "correct_headword"}
    assert verification["before"] == {"reviewed_operation_id": event["operation_id"]}
    assert verification["entry_id"] == "stable-row-1"
    assert pdic.read_bytes() == saved_pdic
    assert image.read_bytes() == saved_image
    assert explicit_verification_counts(
        load_events(journal),
        pdic_sha256=sha256_file(pdic), image_sha256=sha256_file(image),
    ) == {"correct_headword": 1, "not_headword": 0}
    with pytest.raises(ValueError, match="already"):
        _verify(pdic, image, journal, event)
    assert len(load_events(journal)) == 2


def test_explicit_negative_count_without_training_or_raw_export(tmp_path):
    pdic, image, journal, event = _source(tmp_path)
    verify_saved_action(
        journal=journal, pdic_file=pdic, image_file=image,
        operation_id=event["operation_id"], judgment="not_headword",
        explicitly_confirmed=True,
    )
    summary = summarize_local_events(
        journal, pdic, image_path=image, project_id="project-1",
        license_statement="Internal audit only",
    )
    assert summary["verified_negative_labels"] == 1
    assert summary["verified_positive_labels"] == 0
    assert summary["training_labels_exported"] == 0
    encoded = json.dumps(summary)
    assert "old" not in encoded
    assert "new" not in encoded
    assert "stable-row-1" not in encoded


def test_verification_rejects_source_drift_and_missing_identity(tmp_path):
    pdic, image, journal, event = _source(tmp_path)
    pdic.write_bytes(b"changed PDIC")
    with pytest.raises(ValueError, match="Stale"):
        _verify(pdic, image, journal, event)
    pdic.write_bytes(b"saved human PDIC")
    image.write_bytes(b"new image")
    with pytest.raises(ValueError, match="changed source image"):
        _verify(pdic, image, journal, event)
    assert len(load_events(journal)) == 1


def test_verification_requires_matching_ocr_cache_when_attached(tmp_path):
    pdic, image, journal, event = _source(tmp_path, ocr_signature="source-v1")
    with pytest.raises(ValueError, match="OCR cache"):
        _verify(pdic, image, journal, event)
    cache = tmp_path / "ocr.json"
    cache.write_text(json.dumps({"signature": "different"}), encoding="utf-8")
    with pytest.raises(ValueError, match="OCR source changed"):
        _verify(pdic, image, journal, event, ocr_cache=cache)
    cache.write_text(json.dumps({"signature": "source-v1"}), encoding="utf-8")
    assert _verify(pdic, image, journal, event, ocr_cache=cache)["candidate_id"] == "candidate-x"


def test_previous_verified_label_is_stale_after_following_pdic_update(tmp_path):
    pdic, image, journal, event = _source(tmp_path)
    _verify(pdic, image, journal, event)
    pdic.write_bytes(b"later edit")
    assert explicit_verification_counts(
        load_events(journal), pdic_sha256=sha256_file(pdic),
        image_sha256=sha256_file(image),
    ) == {"correct_headword": 0, "not_headword": 0}



def test_two_stale_verification_writers_cannot_publish_duplicate_judgments(tmp_path):
    """Both callers can pass an old pre-lock read; append must recheck under lock."""
    pdic, image, journal, source = _source(tmp_path)
    base = dict(
        page_id=source["page_id"], action="verify",
        before={"reviewed_operation_id": source["operation_id"]},
        after={"judgment": "correct_headword"},
        entry_id=source["entry_id"], pdic_sha256=sha256_file(pdic),
        image_sha256=sha256_file(image),
        verification_status="verified", explicitly_verified=True,
    )
    first = make_event(**base)
    second = make_event(**base)
    assert first["operation_id"] != second["operation_id"]
    append_event(journal, first, pdic_file=pdic)
    before_second_write = journal.read_bytes()
    with pytest.raises(ValueError, match="already verified"):
        append_event(journal, second, pdic_file=pdic)
    assert journal.read_bytes() == before_second_write
    assert len(load_events(journal)) == 2
    assert explicit_verification_counts(
        load_events(journal), pdic_sha256=sha256_file(pdic),
        image_sha256=sha256_file(image),
    )["correct_headword"] == 1


def test_verification_journal_rejects_wrong_source_identity(tmp_path):
    pdic, image, journal, source = _source(tmp_path)
    impostor = make_event(
        page_id=source["page_id"], action="verify",
        before={"reviewed_operation_id": source["operation_id"]},
        after={"judgment": "not_headword"},
        entry_id="different-entry", pdic_sha256=sha256_file(pdic),
        image_sha256=sha256_file(image),
        verification_status="verified", explicitly_verified=True,
    )
    with pytest.raises(ValueError, match="entry identity"):
        append_event(journal, impostor, pdic_file=pdic)
    assert len(load_events(journal)) == 1


def test_verification_does_not_commit_when_image_changes_before_append(tmp_path, monkeypatch):
    """Post-consent source drift must not become a verified judgment."""
    from picture_capture import proofreading_verification as mod

    pdic, image, journal, event = _source(tmp_path)
    original = mod.append_event

    def changed_image(journal_path, review, *, pdic_file, **kwargs):
        image.write_bytes(b"scan replaced after visual inspection")
        return original(journal_path, review, pdic_file=pdic_file, **kwargs)

    monkeypatch.setattr(mod, "append_event", changed_image)
    with pytest.raises(ValueError, match="source .*changed|source .*mismatch"):
        _verify(pdic, image, journal, event)
    assert len(load_events(journal)) == 1
    assert not journal.with_name(journal.name + ".lock").exists()


def test_verification_does_not_commit_when_ocr_cache_changes_before_append(tmp_path, monkeypatch):
    """An OCR signature checked before acquiring the lock can become stale."""
    from picture_capture import proofreading_verification as mod

    pdic, image, journal, event = _source(tmp_path, ocr_signature="ocr-v1")
    cache = tmp_path / "source_ocr.json"
    cache.write_text(json.dumps({"signature": "ocr-v1"}), encoding="utf-8")
    original = mod.append_event

    def changed_ocr(journal_path, review, *, pdic_file, **kwargs):
        cache.write_text(json.dumps({"signature": "later-ocr"}), encoding="utf-8")
        return original(journal_path, review, pdic_file=pdic_file, **kwargs)

    monkeypatch.setattr(mod, "append_event", changed_ocr)
    with pytest.raises(ValueError, match="source .*changed|source .*mismatch"):
        _verify(pdic, image, journal, event, ocr_cache=cache)
    assert len(load_events(journal)) == 1


def test_verified_journal_rechecks_source_bytes_inside_write_lock(tmp_path, monkeypatch):
    """A source changed during atomic publication fails without erasing history."""
    from picture_capture import proofreading_events as mod

    pdic, image, journal, source = _source(tmp_path)
    review = make_event(
        page_id=source["page_id"], action="verify",
        before={"reviewed_operation_id": source["operation_id"]},
        after={"judgment": "correct_headword"},
        entry_id=source["entry_id"], pdic_sha256=sha256_file(pdic),
        image_sha256=sha256_file(image),
        verification_status="verified", explicitly_verified=True,
    )
    before = journal.read_bytes()
    actual_digest = mod.sha256_file
    reads = 0

    def changed_between_two_source_reads(path):
        nonlocal reads
        if Path(path) == image:
            reads += 1
            if reads == 2:
                image.write_bytes(b"changed while journal was locked")
        return actual_digest(path)

    monkeypatch.setattr(mod, "sha256_file", changed_between_two_source_reads)
    with pytest.raises(ValueError, match="source .*changed|source .*mismatch"):
        mod.append_event(
            journal, review, pdic_file=pdic,
            source_checks={image: source["image_sha256"]},
        )
    assert journal.read_bytes() == before


def test_cli_is_explicit_not_training_and_no_visual_auto_approval():
    content = (
        Path(__file__).resolve().parents[1] / "scripts" /
        "verify_proofreading_action.py"
    ).read_text(encoding="utf-8")
    assert "--confirm-visual-review" in content
    assert "if not args.confirm_visual_review:" in content
    assert "verify_saved_action(" in content
    assert "train(" not in content
