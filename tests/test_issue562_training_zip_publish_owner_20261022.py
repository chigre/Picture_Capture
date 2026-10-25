"""Issue #562: one ZIP publication owner, historical ABI, no partial archives."""
from __future__ import annotations

import importlib
import pickle
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest

from picture_capture import training_export
from picture_capture.training import zip_publish


def _staging(tmp_path: Path) -> Path:
    staging = tmp_path / "staging"
    (staging / "子目录").mkdir(parents=True)
    (staging / "z.bin").write_bytes(b"raw\\x00payload")
    (staging / "子目录" / "a.txt").write_bytes("词条\\r\\n".encode("utf-8"))
    return staging


def test_physical_owner_and_exact_public_abi_in_composed_v3() -> None:
    root = Path(training_export.__file__).resolve().parent.parent
    assert Path(zip_publish.__file__).resolve() == root / "training" / "zip_publish.py"
    assert training_export.TrainingExportCancelled is zip_publish.TrainingExportCancelled
    assert training_export.make_training_zip is zip_publish.make_training_zip
    composed = importlib.import_module("picture_capture.training.export_composed")
    assert composed.TrainingExportCancelled is zip_publish.TrainingExportCancelled
    assert composed.make_training_zip is zip_publish.make_training_zip
    facade = (root / "training/export_runtime.py").read_text(encoding="utf-8")
    assert "class TrainingExportCancelled(" not in facade
    assert "def make_training_zip(" not in facade
    assert "temp_zip.replace(zip_path)" in (root / "training" / "zip_publish.py").read_text(encoding="utf-8")


def test_legacy_exception_and_callable_remain_pickle_resolvable() -> None:
    cls = zip_publish.TrainingExportCancelled
    action = zip_publish.make_training_zip
    assert cls.__module__ == action.__module__ == "picture_capture.training_export"
    assert pickle.loads(pickle.dumps(cls)) is cls
    assert pickle.loads(pickle.dumps(action)) is action
    instance = cls("停止")
    restored = pickle.loads(pickle.dumps(instance))
    assert type(restored) is cls and restored.args == ("停止",)


def test_successful_archive_is_atomic_and_preserves_unicode_names_and_bytes(tmp_path) -> None:
    source = _staging(tmp_path)
    target = tmp_path / "训练标记包.zip"
    before = {path.relative_to(source).as_posix(): path.read_bytes() for path in source.rglob("*") if path.is_file()}
    assert training_export.make_training_zip(source, target) == target
    with ZipFile(target) as archive:
        assert archive.namelist() == ["z.bin", "子目录/a.txt"]
        assert {name: archive.read(name) for name in archive.namelist()} == before
    assert {path.relative_to(source).as_posix(): path.read_bytes() for path in source.rglob("*") if path.is_file()} == before
    assert not tuple(tmp_path.glob(f".{target.name}.*.tmp"))


def test_cancellation_mid_archive_keeps_published_archive_byte_exact(tmp_path) -> None:
    source = _staging(tmp_path)
    target = tmp_path / "dataset.zip"
    target.write_bytes(b"existing-published-archive")
    ticks = 0

    def cancel_on_second_file() -> bool:
        nonlocal ticks
        ticks += 1
        return ticks == 3  # first preflight + first file pass, next entry cancels

    with pytest.raises(training_export.TrainingExportCancelled, match="已停止"):
        zip_publish.make_training_zip(source, target, should_stop=cancel_on_second_file)
    assert ticks == 3
    assert target.read_bytes() == b"existing-published-archive"
    assert not tuple(tmp_path.glob(f".{target.name}.*.tmp"))


def test_archive_write_error_rolls_back_without_clobbering_last_good_zip(tmp_path, monkeypatch) -> None:
    source = _staging(tmp_path)
    target = tmp_path / "dataset.zip"
    target.write_bytes(b"last-good-publication")
    original = zip_publish.zipfile.ZipFile.write
    calls = 0

    def broken_write(self, filename, arcname=None, compress_type=None, compresslevel=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic storage failure")
        return original(self, filename, arcname, compress_type, compresslevel)

    monkeypatch.setattr(zip_publish.zipfile.ZipFile, "write", broken_write)
    with pytest.raises(OSError, match="synthetic storage failure"):
        training_export.make_training_zip(source, target)
    assert calls == 2
    assert target.read_bytes() == b"last-good-publication"
    assert not tuple(tmp_path.glob(f".{target.name}.*.tmp"))


def test_leaf_first_import_stays_free_of_legacy_export_gui_and_cycles() -> None:
    script = """
import importlib
import sys
import pickle
owner = importlib.import_module('picture_capture.training.zip_publish')
assert 'picture_capture.training_export' not in sys.modules
assert 'picture_capture.app' not in sys.modules
legacy = importlib.import_module('picture_capture.training_export')
assert legacy.TrainingExportCancelled is owner.TrainingExportCancelled
assert legacy.make_training_zip is owner.make_training_zip
assert pickle.loads(pickle.dumps(owner.TrainingExportCancelled)) is owner.TrainingExportCancelled
assert pickle.loads(pickle.dumps(owner.make_training_zip)) is owner.make_training_zip
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
