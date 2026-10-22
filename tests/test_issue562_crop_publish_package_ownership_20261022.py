"""Issue #562: one real Crop publication owner, with legacy core contracts."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import picture_capture.processing as processing
from picture_capture.crop import publish


def test_crop_publish_physical_owner_and_core_identity() -> None:
    root = Path(publish.__file__).resolve().parents[1]
    assert Path(publish.__file__).resolve() == root / "crop" / "publish.py"
    assert not (root / "processing_publish.py").exists()
    assert importlib.util.find_spec("picture_capture.processing_publish") is None
    assert processing._core._publish_temp_path is publish._publish_temp_path
    assert processing._core._publish_file_transaction is publish._publish_file_transaction
    assert callable(publish.recover_incomplete_crop_publications)


def test_new_owner_journal_remains_project_local(tmp_path: Path) -> None:
    qt = tmp_path / "QT"
    folder = qt / "PWW"
    folder.mkdir(parents=True)
    old = folder / "entry.png"
    old.write_bytes(b"original")
    stage = folder / ".new.tmp"
    stage.write_bytes(b"updated")
    publish._publish_file_transaction([(stage, old)])
    assert old.read_bytes() == b"updated"
    assert publish.recover_incomplete_crop_publications(tmp_path) == 0
    assert not list(folder.glob(".crop-publish-*.json"))
