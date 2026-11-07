"""G1 fail-first: shared ordinary PDIC writer must respect R3 pathname ownership.

Path.exists() follows symlinks, so a dangling symlink in the recovery
journal slot is an existing directory entry even though exists() is false.
This test uses the real shared write_pdic, not the separate restore writer.
"""
from pathlib import Path

import pytest

from picture_capture.io.formats import write_pdic
from picture_capture.models import Entry


def _setup(tmp_path):
    pdic = tmp_path / "001.pdic"
    original = "甲#10#20#10#20#001#@#@\n".encode("utf-8")
    pdic.write_bytes(original)
    marker = pdic.with_name(f".{pdic.name}.r3-inflight.json")
    def save(word="乙"):
        return write_pdic(
            pdic, [Entry(word=word, x=10, y=20)],
            100, ("001", "@", "@"),
        )
    return pdic, original, marker, save


def test_dangling_symlink_marker_must_block_ordinary_pdic_writer(tmp_path):
    pdic, original, marker, save = _setup(tmp_path)
    try:
        marker.symlink_to("nonexistent-r3-journal.json")
    except (OSError, NotImplementedError):
        pytest.skip("OS does not permit creating a symlink")
    assert marker.is_symlink() and not marker.exists()
    with pytest.raises(RuntimeError, match="(R3|marker|恢复|事务)"):
        save()
    assert pdic.read_bytes() == original
    assert marker.is_symlink()


def test_marker_lstat_permission_error_must_fail_closed(tmp_path, monkeypatch):
    pdic, original, marker, save = _setup(tmp_path)
    real_lstat = Path.lstat
    seen = []
    def checked_lstat(self, *args, **kwargs):
        if self == marker:
            seen.append(self)
            raise PermissionError("cannot inspect recovery marker")
        return real_lstat(self, *args, **kwargs)
    monkeypatch.setattr(Path, "lstat", checked_lstat)
    with pytest.raises(PermissionError, match="cannot inspect recovery marker"):
        save()
    assert seen
    assert pdic.read_bytes() == original


def test_regular_marker_still_blocks_ordinary_pdic_writer(tmp_path):
    pdic, original, marker, save = _setup(tmp_path)
    marker.write_bytes(b"pending recovery")
    with pytest.raises(RuntimeError, match="(R3|marker|恢复|事务)"):
        save()
    assert pdic.read_bytes() == original
    assert marker.read_bytes() == b"pending recovery"


def test_no_marker_allows_normal_atomic_pdic_save(tmp_path):
    pdic, original, marker, save = _setup(tmp_path)
    assert save() is True
    assert pdic.read_text(encoding="utf-8") == "乙#10#20#10#20#001#@#@\n"
    assert not marker.exists()
    assert save() is False  # byte-identical write remains a no-op
