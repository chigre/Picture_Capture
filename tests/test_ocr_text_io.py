from __future__ import annotations

from pathlib import Path

import picture_capture.processing as processing
from picture_capture import ocr_text_io


def test_phase7k_processing_reexports_ocr_text_io_helpers() -> None:
    for name in (
        "load_replace_rules",
        "process_ocr_text",
        "export_ocred",
        "import_ocred",
    ):
        assert getattr(processing._core, name) is getattr(ocr_text_io, name)
        assert getattr(processing, name) is getattr(ocr_text_io, name)


def test_ocr_text_rule_loading_and_processing(tmp_path: Path) -> None:
    rules_path = tmp_path / "OCRReplace.txt"
    rules_path.write_text(
        "# ignored\n"
        "N\tAlpha\tBeta\n"
        "R\t[0-9]+\t#\n",
        encoding="utf-8",
    )

    rules = ocr_text_io.load_replace_rules(rules_path)

    assert rules == [
        ("N", "Alpha", "Beta"),
        ("R", "[0-9]+", "#"),
    ]
    assert ocr_text_io.process_ocr_text(
        "'Alpha 123'", rules, lowercase=True
    ) == "beta #"


def test_ocred_roundtrip_preserves_legacy_backtick_format(tmp_path: Path) -> None:
    path = tmp_path / "page.OCRed"
    texts = ["Alpha", "Beta"]

    ocr_text_io.export_ocred(path, texts)

    assert path.read_text(encoding="utf-8") == "000|`Alpha\n001|`Beta\n"
    assert ocr_text_io.import_ocred(path) == texts


def test_phase7k_public_process_assignment_still_mirrors_into_core(monkeypatch) -> None:
    def fake_process(_text, _rules, _lowercase):
        return "patched"

    monkeypatch.setattr(processing, "process_ocr_text", fake_process)

    assert processing._core.process_ocr_text is fake_process
