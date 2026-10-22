"""Issue #562: crop recovery must never consume a journal outside QT.

A journal is untrusted input at project open; its own path must be confined,
not just the absolute paths serialized in its payload.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.crop.publish import (
    _journal_path,
    _recover_journal,
    _write_journal,
    recover_incomplete_crop_publications,
)


def _journal_payload(target: Path, backup: Path, staged: list[Path] | None = None):
    return {
        "version": 1,
        "originals": [
            {"target": str(target), "backup": str(backup), "existed": True},
        ],
        "staged": [str(path) for path in (staged or [])],
    }


@pytest.mark.parametrize("state", ["pending", "committed"])
def test_external_journal_cannot_rollback_or_cleanup_in_project_files(
    tmp_path: Path, state: str,
):
    qt = tmp_path / "project" / "QT"
    folder = qt / "PWW"
    folder.mkdir(parents=True)
    target = folder / "page_WW_001.png"
    backup = folder / ".page_WW_001.png.abc.bak"
    target.write_bytes(b"new page")
    backup.write_bytes(b"old page")

    # This file is outside the QT project boundary, but every path named in
    # its JSON is INSIDE QT. The old payload-only guard would mutate the
    # legitimate in-project files and remove this outside journal.
    external = tmp_path / "outside" / "transactions"
    journal = _journal_path(external, "external", state)
    _write_journal(journal, _journal_payload(target, backup))
    journal_bytes = journal.read_bytes()

    with pytest.raises(ValueError, match="journal is outside its project"):
        _recover_journal(journal, allowed_root=qt)

    assert target.read_bytes() == b"new page"
    assert backup.read_bytes() == b"old page"
    assert journal.read_bytes() == journal_bytes


def test_external_journal_is_rejected_before_parsing_untrusted_json(tmp_path: Path):
    qt = tmp_path / "project" / "QT"
    qt.mkdir(parents=True)
    journal = tmp_path / "external" / ".crop-publish-bad.pending.json"
    journal.parent.mkdir()
    journal.write_bytes(b"not JSON")

    with pytest.raises(ValueError, match="journal is outside its project"):
        _recover_journal(journal, allowed_root=qt)
    assert journal.read_bytes() == b"not JSON"


@pytest.mark.parametrize("state", ["pending", "committed"])
def test_valid_internal_cross_directory_crop_recovery_is_unchanged(
    tmp_path: Path, state: str,
):
    root = tmp_path / "project"
    qt = root / "QT"
    pww = qt / "PWW"
    plans = qt / "CropPlan"
    pww.mkdir(parents=True)
    plans.mkdir()
    image = pww / "page_WW_001.png"
    image_backup = pww / ".page_WW_001.png.test.bak"
    plan = plans / "page.json"
    plan_backup = plans / ".page.json.test.bak"
    staged = plans / ".staged-plan.tmp"
    image.write_bytes(b"new image")
    image_backup.write_bytes(b"old image")
    plan.write_bytes(b"new plan")
    plan_backup.write_bytes(b"old plan")
    staged.write_bytes(b"unpublished")

    journal = _journal_path(pww, "internal", state)
    _write_journal(journal, {
        "version": 1,
        "originals": [
            {"target": str(image), "backup": str(image_backup), "existed": True},
            {"target": str(plan), "backup": str(plan_backup), "existed": True},
        ],
        "staged": [str(staged)],
    })

    assert recover_incomplete_crop_publications(root) == 1
    expected = b"old" if state == "pending" else b"new"
    assert image.read_bytes() == expected + b" image"
    assert plan.read_bytes() == expected + b" plan"
    assert not image_backup.exists()
    assert not plan_backup.exists()
    assert not staged.exists()
    assert not journal.exists()
    assert recover_incomplete_crop_publications(root) == 0


def test_internal_journal_cannot_recover_outside_project_target(tmp_path: Path):
    root = tmp_path / "project"
    qt = root / "QT"
    folder = qt / "PWW"
    folder.mkdir(parents=True)
    scan = root / "source-scan.png"
    scan.write_bytes(b"user-owned scan")
    backup = folder / ".source-scan.png.test.bak"
    backup.write_bytes(b"old bytes")
    journal = _journal_path(folder, "malicious", "pending")
    _write_journal(journal, _journal_payload(scan, backup))

    with pytest.raises(ValueError, match="refers outside its project"):
        recover_incomplete_crop_publications(root)
    assert scan.read_bytes() == b"user-owned scan"
    assert backup.read_bytes() == b"old bytes"
    assert journal.exists()
