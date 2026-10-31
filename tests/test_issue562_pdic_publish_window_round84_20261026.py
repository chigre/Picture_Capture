"""Round 84: protect PDIC when an editor races OCRed sidecar export.

These checks reduce (but do not eliminate) optimistic race windows.
A cross-process atomic compare-and-swap for PDIC is not available here.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr
from picture_capture.ocr.text_io import export_ocred, import_ocred


def _pdic_entry(path: Path, word: str, x: int = 14, y: int = 29) -> None:
    write_pdic(path, [Entry(word, x, y)], 100, ("001", "@", "@"))


@pytest.mark.parametrize("sidecar_preexisting", [True, False])
def test_conflicting_pdic_during_ocred_export_preserves_both_for_review(
    tmp_path, sidecar_preexisting,
):
    pdic = tmp_path / "001.PDIC"
    _pdic_entry(pdic, "original")
    original_pdic = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    if sidecar_preexisting:
        ocred.write_bytes(b"\xef\xbb\xbf000|`old-manual\r\n")
    calls = []

    def export_with_interleaved_manual_edit(path, texts):
        export_ocred(path, texts)
        _pdic_entry(pdic, "proofread-latest", 23, 44)
        calls.append("manual-changed")

    def refuse_pdic_write(*_args):
        calls.append("overwrote-user-data")

    with pytest.raises(RuntimeError, match="PDIC 在 OCRed 导出期间被其他操作修改"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["stale-OCR"], [Entry("stale-OCR", 14, 29)],
            100, ("001", "@", "@"),
            export_ocred=export_with_interleaved_manual_edit,
            write_pdic=refuse_pdic_write,
            expected_pdic_bytes=original_pdic,
        )
    assert calls == ["manual-changed"]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("proofread-latest", 23, 44)
    ]
    # PDIC ownership is lost: even a byte-exact rollback of OCRed would
    # be a unilateral write against the concurrent PDIC correction.
    assert import_ocred(ocred) == ["stale-OCR"]
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("interference", ["edit", "remove", "create"])
def test_stale_source_snapshot_rejects_before_ocred_export(
    tmp_path, interference,
):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"000|`original\n")
    old_ocred = ocred.read_bytes()
    initial = None
    if interference != "create":
        _pdic_entry(pdic, "old")
        initial = pdic.read_bytes()
    if interference == "edit":
        _pdic_entry(pdic, "corrected", 40, 52)
    elif interference == "remove":
        pdic.unlink()
    else:
        _pdic_entry(pdic, "new-created")
    calls = []

    with pytest.raises(RuntimeError, match="发布前 PDIC 已被其他操作修改"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["stale"], [Entry("stale", 14, 29)],
            100, ("001", "@", "@"),
            export_ocred=lambda *_args: calls.append("export"),
            write_pdic=lambda *_args: calls.append("pdic"),
            expected_pdic_bytes=initial,
        )
    assert calls == []
    assert ocred.read_bytes() == old_ocred


def test_unchanged_snapshot_preserves_legacy_order_and_marker_coordinates(tmp_path):
    pdic = tmp_path / "001.PDIC"
    _pdic_entry(pdic, "old", 12, 77)
    old = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    calls = []

    def export(path, words):
        calls.append("export")
        export_ocred(path, words)

    def save(path, entries, width, pages):
        calls.append("pdic")
        return write_pdic(path, entries, width, pages)

    publish_existing_pdic_ocr(
        ocred, pdic, ["recognized"], [Entry("recognized", 12, 77)],
        100, ("001", "@", "@"),
        export_ocred=export, write_pdic=save,
        expected_pdic_bytes=old,
    )
    assert calls == ["export", "pdic"]
    assert import_ocred(ocred) == ["recognized"]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("recognized", 12, 77)
    ]


def test_legacy_direct_publisher_still_accepts_no_snapshot_argument(tmp_path):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "QT" / "001.OCRed"
    publish_existing_pdic_ocr(
        ocred, pdic, ["legacy"], [Entry("legacy", 9, 22)],
        100, ("001", "@", "@"),
        export_ocred=export_ocred, write_pdic=write_pdic,
    )
    assert import_ocred(ocred) == ["legacy"]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [("legacy", 9, 22)]


def test_pdic_change_during_export_never_attempts_ocred_compensation(tmp_path, monkeypatch):
    import picture_capture.ocr.batch_publication as publication

    pdic = tmp_path / "001.PDIC"
    _pdic_entry(pdic, "old")
    before = pdic.read_bytes()
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(b"old")

    def export_with_edit(path, words):
        export_ocred(path, words)
        _pdic_entry(pdic, "user-edited")

    monkeypatch.setattr(publication, "_restore_ocred_bytes",
                        lambda *_args: (_ for _ in ()).throw(OSError("rollback denied")))
    with pytest.raises(RuntimeError, match="拒绝单侧回滚 OCRed"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["new"], [Entry("new", 14, 29)],
            100, ("001", "@", "@"),
            export_ocred=export_with_edit,
            write_pdic=lambda *_args: pytest.fail("must not save stale PDIC"),
            expected_pdic_bytes=before,
        )
    assert read_pdic(pdic)[0].word == "user-edited"
    assert import_ocred(ocred) == ["new"]


def test_round84_publication_guards_both_interference_windows():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture/ocr"
    leaf = (root / "batch_existing_entries.py").read_text(encoding="utf-8")
    publisher = (root / "batch_publication.py").read_text(encoding="utf-8")
    assert "expected_pdic_bytes=source_pdic_bytes" in leaf
    assert "previous_pdic != expected_pdic_bytes" in publisher
    assert "if pdic_after_export != previous_pdic:" in publisher
    assert publisher.index("if pdic_after_export != previous_pdic:") < publisher.index(
        "write_pdic(pdic_path, entries, image_width, pages_info)"
    )
