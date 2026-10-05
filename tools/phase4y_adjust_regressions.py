from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tests/test_next_stage_regressions.py"


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    old_combined = '''    current_start = source.index("    def auto_detect_current(")
    current_end = source.index("    def paddle_detect_current(", current_start)
    current = source[current_start:current_end]
    assert 'if settings.detection_method == "combined":' in current
    assert "ocr_existing_entry_words_from_markers(" in current
    assert "only_blank=True" in current
    assert "融合画线自动补字不得修改任何画线坐标" in current
'''
    new_combined = '''    assert "self._detection_controller_for_call().auto_detect_current(" in source
    controller_source = (
        Path(inspect.getsourcefile(app_module)).parent
        / "ui" / "controllers" / "detection.py"
    ).read_text(encoding="utf-8")
    current_start = controller_source.index("    def auto_detect_current(")
    current_end = controller_source.index("    def paddle_detect_current(", current_start)
    current = controller_source[current_start:current_end]
    assert 'if settings.detection_method == "combined":' in current
    assert "ocr_existing_entry_words_from_markers(" in current
    assert "only_blank=True" in current
    assert "融合画线自动补字不得修改任何画线坐标" in current
'''
    if old_combined not in text:
        raise RuntimeError("combined current-page ownership block not found")
    text = text.replace(old_combined, new_combined, 1)

    old_background = '''    for name, next_name in (
        ("auto_detect_current", "paddle_detect_current"),
        ("ocr_current", "export_text"),
        ("import_legacy_words", "_default_old_new_compare_source"),
    ):
        start = text.index(f"    def {name}(", app_start)
        end = text.index(f"\\n    def {next_name}(", start)
        block = text[start:end]
        assert "self._start_batch_task(" in block
'''
    new_background = '''    auto_start = text.index("    def auto_detect_current(", app_start)
    auto_end = text.index("\\n    def _detection_controller_for_call", auto_start)
    auto_wrapper = text[auto_start:auto_end]
    assert "self._detection_controller_for_call().auto_detect_current(" in auto_wrapper

    detection_text = (
        root / "src" / "picture_capture" / "ui" / "controllers" / "detection.py"
    ).read_text(encoding="utf-8")
    current_start = detection_text.index("    def auto_detect_current(")
    current_end = detection_text.index("\\n    def paddle_detect_current", current_start)
    current_block = detection_text[current_start:current_end]
    assert "app._start_batch_task(" in current_block

    for name, next_name in (
        ("ocr_current", "export_text"),
        ("import_legacy_words", "_default_old_new_compare_source"),
    ):
        start = text.index(f"    def {name}(", app_start)
        end = text.index(f"\\n    def {next_name}(", start)
        block = text[start:end]
        assert "self._start_batch_task(" in block
'''
    if old_background not in text:
        raise RuntimeError("background ownership loop not found")
    text = text.replace(old_background, new_background, 1)

    PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
