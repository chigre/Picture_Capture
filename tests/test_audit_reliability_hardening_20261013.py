"""Regression coverage for migration, crop crash recovery, and PNG normalization."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from picture_capture.crop.export_output import normalize_project_crop_widths
from picture_capture.crop.settings import load_crop_settings, normalize_crop_settings_payload
from picture_capture.models import AppSettings
from picture_capture.processing_publish import (
    _journal_path,
    _publish_file_transaction,
    _write_journal,
    recover_incomplete_crop_publications,
)
from picture_capture.project_storage import (
    _same_file_payload,
    migrate_legacy_project,
    project_activity_path,
)


def _png(path: Path, width: int, *, color: str = "black") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, 4), color).save(path)


def test_migration_same_size_different_bytes_is_not_verified(tmp_path):
    a, b = tmp_path / "source.pdic", tmp_path / "copy.pdic"
    a.write_bytes(b"ABCDEF")
    b.write_bytes(b"XYZ123")
    assert not _same_file_payload(a, b)


def test_migration_casefold_collision_preserves_sources(tmp_path):
    (tmp_path / "a.pdic").write_text("alpha", encoding="utf-8")
    (tmp_path / "a.PDIC").write_text("other", encoding="utf-8")
    # On Windows these two names cannot coexist, so the Linux/macOS case is
    # tested on case-sensitive filesystems and skipped on case-insensitive ones.
    if len(list(tmp_path.glob("a.*"))) < 2:
        pytest.skip("filesystem is case insensitive")
    with pytest.raises(RuntimeError, match="冲突"):
        migrate_legacy_project(tmp_path, "test")
    assert (tmp_path / "a.pdic").read_text() == "alpha"
    assert (tmp_path / "a.PDIC").read_text() == "other"
    assert not (tmp_path / "_PictureCapture").exists()


def test_crop_publish_rolls_back_when_os_replace_fails(tmp_path, monkeypatch):
    from picture_capture import processing_publish as publish

    old, staged = tmp_path / "target.txt", tmp_path / ".target.tmp"
    old.write_text("old")
    staged.write_text("new")
    original_replace = publish.os.replace

    def reject_new(source, target):
        if Path(source) == staged:
            raise OSError("simulated disk failure")
        return original_replace(source, target)

    monkeypatch.setattr(publish.os, "replace", reject_new)
    with pytest.raises(OSError, match="disk failure"):
        _publish_file_transaction([(staged, old)])
    assert old.read_text() == "old"
    assert not list(tmp_path.glob(".crop-publish-*.json"))


def test_crop_startup_rolls_back_interrupted_transaction(tmp_path):
    qt = tmp_path / "QT"
    folder = qt / "PWW"
    folder.mkdir(parents=True)
    target, backup = folder / "p_WW_001.png", folder / ".p_WW_001.png.bak"
    target.write_bytes(b"new")
    backup.write_bytes(b"old")
    journal = _journal_path(folder, "test")
    _write_journal(journal, {
        "version": 1,
        "originals": [{"target": str(target), "backup": str(backup), "existed": True}],
        "staged": [],
    })
    assert recover_incomplete_crop_publications(tmp_path) == 1
    assert target.read_bytes() == b"old"
    assert not journal.exists()


def test_crop_startup_keeps_committed_files(tmp_path):
    folder = tmp_path / "QT" / "PWW"
    folder.mkdir(parents=True)
    target, backup = folder / "p_WW_001.png", folder / ".p_WW_001.png.bak"
    target.write_bytes(b"new")
    backup.write_bytes(b"old")
    journal = _journal_path(folder, "test", "committed")
    _write_journal(journal, {
        "version": 1,
        "originals": [{"target": str(target), "backup": str(backup), "existed": True}],
        "staged": [],
    })
    assert recover_incomplete_crop_publications(tmp_path) == 1
    assert target.read_bytes() == b"new"
    assert not backup.exists()


def test_auto_width_uses_natural_not_previously_padded_width(tmp_path):
    folder = tmp_path / "QT" / "PWW"
    short = folder / "a_WW_001(1).png"
    long = folder / "b_WW_001(1).png"
    _png(short, 15)
    _png(long, 12)
    (folder / "a.PWWWidths.json").write_text(
        json.dumps({short.name: 5}), encoding="utf-8",
    )
    (folder / "b.PWWWidths.json").write_text(
        json.dumps({long.name: 12}), encoding="utf-8",
    )
    stats = normalize_project_crop_widths(tmp_path, {"entry_width_mode": "auto"})
    assert stats["target_width"] == 12
    with Image.open(short) as image:
        assert image.width == 12


def test_alpha_change_works_without_width_change(tmp_path):
    path = tmp_path / "QT" / "PWW" / "a_WW_001.png"
    _png(path, 8, color="white")
    settings = {
        "entry_width_mode": "fixed", "entry_fixed_width": 8,
        "entry_transparent_background": True,
    }
    result = normalize_project_crop_widths(tmp_path, settings)
    assert result["entries_padded"] == 1
    with Image.open(path) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 0
    assert normalize_project_crop_widths(tmp_path, settings)["entries_padded"] == 0


def test_crop_normalization_cancel_preserves_restorable_png(tmp_path):
    path = tmp_path / "QT" / "PWW" / "a_WW_001.png"
    _png(path, 5)
    with pytest.raises(InterruptedError):
        normalize_project_crop_widths(
            tmp_path, {"entry_width_mode": "fixed", "entry_fixed_width": 9},
            cancelled=lambda: True,
        )
    with Image.open(path) as image:
        assert image.size == (5, 4)


def test_bad_crop_settings_version_is_safe_and_corrupt_json_is_reported(tmp_path):
    defaults = normalize_crop_settings_payload(None, AppSettings())
    invalid = normalize_crop_settings_payload({
        "version": "broken", "coordinate_space": defaults["coordinate_space"],
    }, AppSettings())
    assert invalid == defaults
    config = tmp_path / "QT" / "_CropSettings.json"
    config.parent.mkdir()
    config.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="切图设置文件损坏"):
        load_crop_settings(tmp_path, AppSettings())


def test_page_artifact_edit_invalidates_metadata_clock(tmp_path, monkeypatch):
    from picture_capture import project_center_metadata_cache as cache
    from picture_capture.formats import write_pdic
    from picture_capture.models import Entry

    monkeypatch.setattr(cache, "user_config_root", lambda: tmp_path / "config")
    project = tmp_path / "legacy_project"
    project.mkdir()
    (project / "1.png").write_bytes(b"scan")
    from picture_capture.recent_projects import recent_project_details
    row = {"path": str(project)}
    cache.store_details([recent_project_details(row)])
    assert cache.cached_details(project) is not None
    write_pdic(project / "1.pdic", [Entry("word", 2, 3)], 100, ("1", "@", "@"))
    assert project_activity_path(project).is_file()
    assert cache.cached_details(project) is None
