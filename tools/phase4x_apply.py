from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/picture_capture/app.py"


def replace_method(text: str, name: str, next_name: str, replacement: str) -> str:
    start = text.index(f"    def {name}(")
    end = text.index(f"    def {next_name}(", start)
    return text[:start] + replacement + text[end:]


def main() -> None:
    text = APP.read_text(encoding="utf-8")
    replacement = (
        "    def batch_ocr(self) -> None:\n"
        "        self._detection_controller_for_call().batch_ocr()\n\n"
    )
    updated = replace_method(text, "batch_ocr", "batch_split_whole", replacement)
    if updated == text:
        raise RuntimeError("Phase 4X app patch produced no change")
    APP.write_text(updated, encoding="utf-8")

    controller = (
        ROOT / "src/picture_capture/ui/controllers/detection.py"
    ).read_text(encoding="utf-8")
    if "    def batch_ocr(self) -> None:" not in controller:
        raise RuntimeError("DetectionController.batch_ocr missing")

    tests = (ROOT / "tests/test_ui_detection_controller.py").read_text(encoding="utf-8")
    if '"batch_ocr": "batch_ocr"' not in tests:
        raise RuntimeError("Phase 4X wiring assertion missing")


if __name__ == "__main__":
    main()
