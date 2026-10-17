"""An unresolved R3 recovery marker must quarantine ordinary app writes."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.app import PictureCaptureApp
from picture_capture.formats import pdic_path, write_pdic
from picture_capture.models import Entry
from picture_capture.proofreading_transactions import _recovery_path


@pytest.mark.parametrize("sync_editors", [False, True])
def test_unresolved_r3_marker_refuses_regular_pdic_save_before_editor_sync(
    tmp_path, monkeypatch, sync_editors,
):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic-only-not-a-private-scan")
    pdic = pdic_path(page)
    write_pdic(pdic, [Entry("original", 10, 20)], 100, ("synthetic", "@", "@"))
    old = pdic.read_bytes()
    marker = _recovery_path(page)
    marker.write_bytes(b"unresolved-mixed-state")
    fake = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path), current_page=page,
        image=SimpleNamespace(width=100),
    )
    def forbidden_write(*args, **kwargs):
        pytest.fail("PDIC must not be overwritten while R3 recovery is unresolved")
    monkeypatch.setattr("picture_capture.app.write_pdic", forbidden_write)
    with pytest.raises(RuntimeError, match="Unresolved R3 transaction"):
        PictureCaptureApp.save_pdic(fake, sync_editors=sync_editors)
    assert pdic.read_bytes() == old
    assert marker.exists()
