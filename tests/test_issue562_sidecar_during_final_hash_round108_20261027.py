"""Round 108: concurrent sidecar edits during the last source-image hash."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr import batch_existing_entries as worker
from picture_capture.ocr.text_io import export_ocred, render_ocred_bytes
from picture_capture.persistence.page_sections import read_page_sections


@pytest.mark.parametrize("fault", ["pdic_replace", "pdic_remove", "ocred_replace", "ocred_remove", "none"])
def test_final_provenance_hash_catches_sidecar_edit(tmp_path, monkeypatch, fault):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (100, 120), "white").save(page)
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("before", 17, 43)], 100, ("001", "@", "@"))
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"old")
    original_hash = worker._source_image_sha256
    calls = {"count": 0}

    def hash_with_late_edit(path):
        result = original_hash(path)
        calls["count"] += 1
        # Last hash belongs to the worker's post-reopen source validation.
        if calls["count"] == 6:
            if fault == "pdic_replace":
                pdic.write_bytes(b"manual PDIC edit")
            elif fault == "pdic_remove":
                pdic.unlink()
            elif fault == "ocred_replace":
                ocred.write_bytes(b"manual OCRed edit")
            elif fault == "ocred_remove":
                ocred.unlink()
        return result

    monkeypatch.setattr(worker, "_source_image_sha256", hash_with_late_edit)
    deps = {
        "pdic_path": lambda p: p.with_suffix(".PDIC"),
        "read_pdic": read_pdic,
        "Image": Image,
        "normalize_page_rgb": lambda opened: opened.copy().convert("RGB"),
        "effective_page_settings": lambda s, _size, _index: s,
        "page_template_analysis_image": lambda image, _s, _i: image,
        "read_page_sections": read_page_sections,
        "sort_entries_reading_order": lambda entries, _geo, _sections: entries,
        "derive_geometry": lambda *_: object(),
        "ocr_entries": lambda *_args, **_kwargs: ["recognized"],
        "qt_root": lambda root: root / "QT",
        "export_ocred": export_ocred,
        "write_pdic": write_pdic,
    }
    run = lambda: worker.process_existing_pdic_page(
        page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"), deps=deps,
    )
    if fault == "none":
        assert run() == 1
    else:
        # Replacement is a byte-version conflict; deletion is a read failure.
        # Both must be reported without compensating either committed sidecar.
        message = (
            "页面来源最终核验后无法再次读取"
            if fault.endswith("_remove")
            else "页面来源最终核验期间"
        )
        with pytest.raises(RuntimeError, match=message):
            run()
    assert calls["count"] == 6
    if fault == "pdic_replace":
        assert pdic.read_bytes() == b"manual PDIC edit"
    elif fault == "pdic_remove":
        assert not pdic.exists()
    else:
        assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [("recognized", 17, 43)]
    if fault == "ocred_replace":
        assert ocred.read_bytes() == b"manual OCRed edit"
    elif fault == "ocred_remove":
        assert not ocred.exists()
    else:
        assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))
