"""Issue #503: R3 recovery markers must fail closed even if nonregular.

A dangling symlink must never look like an absent journal, and a directory
or symlink must never be followed as a trusted transaction document.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import stat

import pytest

from picture_capture.io.formats import pdic_path, write_pdic
from picture_capture.models import Entry
from picture_capture.proofreading import transactions as tx


def _page(tmp_path):
    page = tmp_path / "001.png"
    page.write_bytes(b"synthetic test image")
    pdic = pdic_path(page)
    write_pdic(pdic, [Entry("original", 13, 29)], 100, ("001", "@", "@"))
    return page, pdic, tx._recovery_path(page)


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_nonregular_marker_is_not_ignored_or_followed(tmp_path, kind):
    page, pdic, marker = _page(tmp_path)
    before = pdic.read_bytes()
    outside = tmp_path / "outside-journal.json"
    outside.write_bytes(b'{"untrusted":true}')
    if kind == "directory":
        marker.mkdir()
    else:
        try:
            marker.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"symlink creation restricted on this platform: {exc}")

    assert tx._marker_present(marker)
    with pytest.raises(ValueError, match="not a regular file"):
        tx._verified_recovery(page)
    with pytest.raises(ValueError, match="not a regular file"):
        tx.recover_pending_for_page(page)
    with pytest.raises(RuntimeError, match="Unresolved R3 recovery marker"):
        tx._stage_recovery(page, [("pdic", before, b"new PDIC")])
    assert pdic.read_bytes() == before
    assert outside.read_bytes() == b'{"untrusted":true}'
    assert tx._marker_present(marker)


def test_dangling_symlink_blocks_new_r3_transaction(tmp_path):
    page, pdic, marker = _page(tmp_path)
    before = pdic.read_bytes()
    missing = tmp_path / "no-such-file.json"
    try:
        marker.symlink_to(missing)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation restricted on this platform: {exc}")

    assert not marker.exists()  # This was the original bypass.
    assert tx._marker_present(marker)
    with pytest.raises(ValueError, match="not a regular file"):
        tx.recover_pending_for_page(page)
    with pytest.raises(RuntimeError, match="Unresolved R3 recovery marker"):
        tx._stage_recovery(page, [("pdic", before, b"new PDIC")])
    assert marker.is_symlink()
    assert not missing.exists()
    assert pdic.read_bytes() == before


def test_dangling_link_guard_is_cross_platform_without_symlink_privileges(
    tmp_path, monkeypatch,
):
    page, pdic, marker = _page(tmp_path)
    original_lstat = Path.lstat
    real = pdic.read_bytes()

    def simulate_dangling_link(path):
        if path == marker:
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777)
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", simulate_dangling_link)
    assert tx._marker_present(marker)
    with pytest.raises(ValueError, match="not a regular file"):
        tx.recover_pending_for_page(page)
    with pytest.raises(RuntimeError, match="Unresolved R3 recovery marker"):
        tx._stage_recovery(page, [("pdic", real, b"new")])
    assert pdic.read_bytes() == real


def test_unreadable_marker_stat_never_approves_recovery_or_new_stage(
    tmp_path, monkeypatch,
):
    page, pdic, marker = _page(tmp_path)
    before = pdic.read_bytes()
    denied = PermissionError("R3 directory entry cannot be inspected")
    original_lstat = Path.lstat

    def deny_marker(path):
        if path == marker:
            raise denied
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", deny_marker)
    with pytest.raises(PermissionError) as caught:
        tx.recover_pending_for_page(page)
    assert caught.value is denied
    with pytest.raises(PermissionError) as caught:
        tx._stage_recovery(page, [("pdic", before, b"new")])
    assert caught.value is denied
    assert pdic.read_bytes() == before


def test_marker_unlink_silently_skipped_keeps_page_quarantined(
    tmp_path, monkeypatch,
):
    page, pdic, marker = _page(tmp_path)
    before = pdic.read_bytes()
    tx._stage_recovery(page, [("pdic", before, before.replace(b"original", b"changed"))])
    original_unlink = Path.unlink
    removed = []

    def pretend_unlink(path, *args, **kwargs):
        if path == marker:
            removed.append(path)
            return None
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", pretend_unlink)
    assert tx.recover_pending_for_page(page) is False
    assert removed == [marker]
    assert tx._marker_present(marker)
    assert pdic.read_bytes() == before


def test_absent_marker_and_real_regular_journal_still_recover_normally(tmp_path):
    page, pdic, marker = _page(tmp_path)
    before = pdic.read_bytes()
    updated = before.replace(b"original", b"changed")
    assert not tx._marker_present(marker)
    assert tx.recover_pending_for_page(page)
    tx._stage_recovery(page, [("pdic", before, updated)])
    assert tx._marker_present(marker)
    tx._publish(pdic, updated)
    assert tx.recover_pending_for_page(page)
    assert pdic.read_bytes() == updated
    assert not tx._marker_present(marker)
