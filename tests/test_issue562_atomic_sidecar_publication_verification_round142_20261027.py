"""Round 142: successful return from os.replace is not proof of PDIC/PPP publication.

No retries or unilateral compensation are allowed when an adapter silently
does nothing or an external writer replaces the target during publication.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.io import formats
from picture_capture.models import Entry, PolygonRegion


ORIGINAL = b"human-maintained sidecar before batch"
FOREIGN = b"new manual edit published during atomic replacement"


def _target(tmp_path, kind):
    target = tmp_path / ("001.PDIC" if kind == "pdic" else "001.PPP")
    target.write_bytes(ORIGINAL)
    return target


def _save(kind, target):
    if kind == "pdic":
        return formats.write_pdic(
            target, [Entry("lemma", 17, 43)], 100, ("001", "@", "@")
        )
    return formats.write_ppp(
        target,
        [PolygonRegion(label="illustration", points=[(7, 9), (19, 25)])],
        "001",
    )


@pytest.mark.parametrize("kind", ["pdic", "ppp"])
def test_replace_noop_is_not_reported_as_success_and_staging_is_cleaned(
    tmp_path, monkeypatch, kind,
):
    target = _target(tmp_path, kind)
    replaces = []
    artifact_notifications = []

    def no_op_replace(source, dest):
        replaces.append((source, dest))
        # A faulty adapter reports success without moving the staging file.

    monkeypatch.setattr(formats.os, "replace", no_op_replace)
    monkeypatch.setattr(
        formats, "note_page_artifact_edit", artifact_notifications.append,
    )

    with pytest.raises(RuntimeError, match="without a verified byte-exact publication"):
        _save(kind, target)

    assert len(replaces) == 1
    assert Path(replaces[0][1]) == target
    assert target.read_bytes() == ORIGINAL
    assert not artifact_notifications
    assert not list(tmp_path.glob(f".{target.name}.*.tmp"))


@pytest.mark.parametrize("kind", ["pdic", "ppp"])
def test_foreign_edit_after_atomic_replace_is_not_rolled_back(
    tmp_path, monkeypatch, kind,
):
    target = _target(tmp_path, kind)
    actual_replace = formats.os.replace
    writes = []
    artifact_notifications = []

    def replace_and_proofread(source, dest):
        writes.append(True)
        actual_replace(source, dest)
        Path(dest).write_bytes(FOREIGN)

    monkeypatch.setattr(formats.os, "replace", replace_and_proofread)
    monkeypatch.setattr(
        formats, "note_page_artifact_edit", artifact_notifications.append,
    )

    with pytest.raises(RuntimeError, match="without a verified byte-exact publication"):
        _save(kind, target)

    assert writes == [True]
    assert target.read_bytes() == FOREIGN
    assert not artifact_notifications
    assert not list(tmp_path.glob(f".{target.name}.*.tmp"))


@pytest.mark.parametrize("kind", ["pdic", "ppp"])
def test_post_replace_disk_read_denied_reports_exact_verification_error(
    tmp_path, monkeypatch, kind,
):
    target = _target(tmp_path, kind)
    original_read = Path.read_bytes
    actual_replace = formats.os.replace
    committed = []
    denied = PermissionError("sidecar cannot be re-read after replace")
    artifact_notifications = []

    def replace_and_mark(source, dest):
        actual_replace(source, dest)
        committed.append(True)

    def read_with_denial(path):
        if path == target and committed:
            raise denied
        return original_read(path)

    monkeypatch.setattr(formats.os, "replace", replace_and_mark)
    monkeypatch.setattr(Path, "read_bytes", read_with_denial)
    monkeypatch.setattr(
        formats, "note_page_artifact_edit", artifact_notifications.append,
    )

    with pytest.raises(RuntimeError, match="disk state cannot be verified") as caught:
        _save(kind, target)

    assert caught.value.verification_error is denied
    assert caught.value.__cause__ is denied
    assert committed == [True]
    assert not artifact_notifications
    assert original_read(target) != ORIGINAL
    assert not list(tmp_path.glob(f".{target.name}.*.tmp"))


@pytest.mark.parametrize("kind", ["pdic", "ppp"])
def test_confirmed_atomic_publication_preserves_saved_bytes_and_coordinates(
    tmp_path, kind,
):
    target = _target(tmp_path, kind)
    assert _save(kind, target) is True
    saved = target.read_text(encoding="utf-8")
    if kind == "pdic":
        assert saved.splitlines() == ["lemma#17#43#17#43#001#@#@"]
    else:
        assert "7,9" in saved
        assert "19,25" in saved
    assert not list(tmp_path.glob(f".{target.name}.*.tmp"))
