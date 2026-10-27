"""Round 81: never rollback only OCRed after an ambiguous PDIC commit.

The canonical PDIC writer may successfully swap on-disk data but raise from
post-commit bookkeeping. Report this rather than manufacture mismatched
PDIC/OCRed versions by restoring only the sidecar.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.models import Entry
from picture_capture.io import formats
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr
from picture_capture.ocr.text_io import export_ocred, import_ocred


@pytest.mark.parametrize("had_pdic", [False, True])
def test_pdic_writer_that_commits_then_raises_does_not_rollback_ocred(
    tmp_path, had_pdic,
):
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir()
    export_ocred(ocred, ["old"])
    pdic = tmp_path / "001.PDIC"
    if had_pdic:
        pdic.write_bytes(b"old#10#20#10#20#001#@#@\n")

    def committed_then_failed(path, entries, width, pages):
        formats.write_pdic(path, entries, width, pages)
        raise RuntimeError("post-commit failure")

    with pytest.raises(RuntimeError, match="磁盘 PDIC 已发生变化") as caught:
        publish_existing_pdic_ocr(
            ocred, pdic, ["new"], [Entry("new", 10, 20)], 100,
            ("001", "@", "@"),
            export_ocred=export_ocred,
            write_pdic=committed_then_failed,
        )
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert "post-commit failure" in str(caught.value.__cause__)
    assert import_ocred(ocred) == ["new"]
    assert pdic.read_text(encoding="utf-8").startswith("new#10#20#")
    assert list(ocred.parent.glob(".001.OCRed.*.tmp")) == []


def test_real_pdic_post_commit_bookkeeping_failure_preserves_both_new_files(
    tmp_path, monkeypatch,
):
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir()
    export_ocred(ocred, ["old"])
    pdic = tmp_path / "001.PDIC"
    formats.write_pdic(pdic, [Entry("old", 8, 16)], 100, ("001", "@", "@"))

    def fail_after_commit(_path):
        raise RuntimeError("edit clock failed after data publication")

    monkeypatch.setattr(formats, "note_page_artifact_edit", fail_after_commit)
    with pytest.raises(RuntimeError, match="磁盘 PDIC 已发生变化"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["new"], [Entry("new", 8, 16)], 100,
            ("001", "@", "@"),
            export_ocred=export_ocred,
            write_pdic=formats.write_pdic,
        )
    assert import_ocred(ocred) == ["new"]
    assert pdic.read_text(encoding="utf-8").startswith("new#8#16#")


def test_pdic_unchanged_error_rolls_back_ocred_without_touching_pdic(tmp_path):
    ocred = tmp_path / "001.OCRed"
    export_ocred(ocred, ["old"])
    original_ocred = ocred.read_bytes()
    pdic = tmp_path / "001.PDIC"
    pdic.write_bytes(b"old#9#19#9#19#001#@#@\n")
    original_pdic = pdic.read_bytes()

    def failed_without_commit(_path, _entries, _width, _pages):
        raise OSError("disk denied")

    with pytest.raises(OSError, match="disk denied"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["new"], [Entry("new", 9, 19)], 100,
            ("001", "@", "@"),
            export_ocred=export_ocred,
            write_pdic=failed_without_commit,
        )
    assert ocred.read_bytes() == original_ocred
    assert pdic.read_bytes() == original_pdic


def test_pdic_modified_outside_canonical_writer_reports_ambiguous_state(tmp_path):
    ocred = tmp_path / "001.OCRed"
    export_ocred(ocred, ["old"])
    pdic = tmp_path / "001.PDIC"
    pdic.write_bytes(b"old")

    def partial_then_failed(path, *_args):
        path.write_bytes(b"partial")
        raise OSError("partial writer failed")

    with pytest.raises(RuntimeError, match="磁盘 PDIC 已发生变化"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["new"], [Entry("new", 1, 2)], 100,
            ("001", "@", "@"),
            export_ocred=export_ocred,
            write_pdic=partial_then_failed,
        )
    # The pair is explicitly flagged for recovery, rather than pretending to
    # have rolled back PDIC that has already changed.
    assert pdic.read_bytes() == b"partial"
    assert import_ocred(ocred) == ["new"]



def test_failed_pdic_verification_never_reverts_only_ocred(tmp_path, monkeypatch):
    ocred = tmp_path / "001.OCRed"
    export_ocred(ocred, ["old"])
    pdic = tmp_path / "001.PDIC"
    pdic.write_bytes(b"old")

    original_read = Path.read_bytes
    count = {"pdic": 0}
    writer_error = OSError("writer denied")
    verification_error = PermissionError("PDIC read denied after writer error")

    def read_with_post_error(self):
        if self == pdic:
            count["pdic"] += 1
            # Read 1 snapshots the pre-export PDIC; read 2 verifies it
            # before calling the writer; read 3 verifies an ambiguous
            # writer failure. Inject at read 3 to exercise this contract.
            if count["pdic"] == 3:
                raise verification_error
        return original_read(self)

    monkeypatch.setattr(Path, "read_bytes", read_with_post_error)
    with pytest.raises(RuntimeError, match="无法读取 PDIC 确认是否已提交") as caught:
        publish_existing_pdic_ocr(
            ocred, pdic, ["new"], [Entry("new", 1, 2)], 100,
            ("001", "@", "@"),
            export_ocred=export_ocred,
            write_pdic=lambda *_args: (_ for _ in ()).throw(writer_error),
        )
    # The ownership read is the immediate failure, but both original
    # exception objects must survive for recovery tooling.
    assert caught.value.publication_error is writer_error
    assert caught.value.verification_error is verification_error
    assert caught.value.__cause__ is verification_error
    assert count["pdic"] == 3
    assert import_ocred(ocred) == ["new"]
    assert original_read(pdic) == b"old"

def test_ambiguous_pdic_boundary_is_checked_before_ocred_compensation():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture/ocr"
    source = (root / "batch_publication.py").read_text(encoding="utf-8")
    assert "current_pdic != previous_pdic" in source
    # Round 82 also compensates OCRed-export failures *before* PDIC is
    # called. Restrict this ordering assertion to the PDIC error handler.
    pdic_handler = source.split("except Exception as pdic_error:", 1)[1]
    assert pdic_handler.index("if current_pdic != previous_pdic:") < pdic_handler.index(
        "_restore_ocred_if_unchanged("
    )
    # Compensation now rechecks PDIC after staging, before replace/unlink.
    assert "verify_before_mutation=verify_pdic_before_rollback" in pdic_handler
