"""Round 141: PDIC/PPP atomic sidecar writers preserve both filesystem failures.

A failed atomic publication must not be hidden by a second failure when
cleaning up its uncommitted .tmp staging file.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.io import formats
from picture_capture.models import Entry, PolygonRegion


ORIGINAL = b"existing human sidecar bytes"


def _save(kind: str, path: Path):
    if kind == "pdic":
        return formats.write_pdic(path, [Entry("new", 17, 43)], 100, ("001", "@", "@"))
    return formats.write_ppp(
        path, [PolygonRegion(label="illustration", points=[(1, 2), (3, 4)])],
        "001",
    )


def _target(tmp_path: Path, kind: str) -> Path:
    target = tmp_path / ("001.PDIC" if kind == "pdic" else "001.PPP")
    target.write_bytes(ORIGINAL)
    return target


@pytest.mark.parametrize("kind", ["pdic", "ppp"])
@pytest.mark.parametrize("fault", ["replace", "fsync"])
def test_failed_publish_and_failed_cleanup_preserve_both_exceptions(
    tmp_path, monkeypatch, kind, fault,
):
    target = _target(tmp_path, kind)
    publication_error = OSError("atomic staging or replacement failed")
    cleanup_error = PermissionError("staging file removal denied")
    cleanup_attempts = []
    original_unlink = Path.unlink

    def blocked_unlink(path, *args, **kwargs):
        if path.suffix == ".tmp":
            cleanup_attempts.append(path)
            raise cleanup_error
        return original_unlink(path, *args, **kwargs)

    def reject(*_args, **_kwargs):
        raise publication_error

    monkeypatch.setattr(Path, "unlink", blocked_unlink)
    monkeypatch.setattr(formats.os, fault, reject)

    with pytest.raises(RuntimeError, match="publication failed.*cleanup also failed") as caught:
        _save(kind, target)

    assert caught.value.publication_error is publication_error
    assert caught.value.cleanup_error is cleanup_error
    assert caught.value.__cause__ is publication_error
    assert target.read_bytes() == ORIGINAL
    assert len(cleanup_attempts) == 1
    assert cleanup_attempts[0].exists()
    assert sorted(tmp_path.glob(f".{target.name}.*.tmp")) == cleanup_attempts


@pytest.mark.parametrize("kind", ["pdic", "ppp"])
def test_successful_staging_cleanup_preserves_primary_write_exception(
    tmp_path, monkeypatch, kind,
):
    target = _target(tmp_path, kind)
    publication_error = OSError("replace before mutation failed")

    def reject(*_args, **_kwargs):
        raise publication_error

    monkeypatch.setattr(formats.os, "replace", reject)

    with pytest.raises(OSError) as caught:
        _save(kind, target)

    assert caught.value is publication_error
    assert target.read_bytes() == ORIGINAL
    assert not list(tmp_path.glob(f".{target.name}.*.tmp"))


@pytest.mark.parametrize("kind", ["pdic", "ppp"])
def test_replace_applied_then_threw_does_not_mask_error_or_leave_stage(
    tmp_path, monkeypatch, kind,
):
    target = _target(tmp_path, kind)
    publication_error = OSError("post-replace callback error")
    actual_replace = formats.os.replace

    def replace_then_raise(src, dst):
        actual_replace(src, dst)
        raise publication_error

    monkeypatch.setattr(formats.os, "replace", replace_then_raise)
    with pytest.raises(OSError) as caught:
        _save(kind, target)

    assert caught.value is publication_error
    assert target.read_bytes() != ORIGINAL
    assert not list(tmp_path.glob(f".{target.name}.*.tmp"))


def test_normal_pdic_ppp_bytes_and_source_pixel_coordinates(tmp_path):
    pdic = tmp_path / "001.PDIC"
    ppp = tmp_path / "001.PPP"

    assert formats.write_pdic(
        pdic, [Entry("alpha", 17, 43)], 100, ("001", "@", "@")
    ) is True
    assert formats.write_ppp(
        ppp, [PolygonRegion(label="illustration", points=[(1, 2), (3, 4)])],
        "001",
    ) is True

    assert pdic.read_text(encoding="utf-8").splitlines() == [
        "alpha#17#43#17#43#001#@#@"
    ]
    assert "1,2" in ppp.read_text(encoding="utf-8")
    assert "3,4" in ppp.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".*.tmp"))
