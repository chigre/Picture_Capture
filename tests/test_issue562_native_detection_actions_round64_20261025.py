"""Issue #562 Round 64: OCR-disabled native Tk action guards and ordinary fallback."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_live_tk_ocr_actions_guard_before_any_backend_invocation():
    source = (ROOT / "scripts/gui_project_roundtrip_smoke.py").read_text(
        encoding="utf-8",
    )
    ast.parse(source)
    for required in (
        "app.run_ocr_draw_action()",
        "app.run_combined_draw_action()",
        "app.run_normal_draw_action()",
        '("paddle_use_paddleocr", False)',
        '("paddle_compare_tesseract", False)',
        '("paddle_enable_lens", True)',
        'app.settings.paddle_lens_mode = "off"',
        'app.settings.paddle_tesseract_rescue = False',
        "forbidden_dispatch.assert_not_called()",
        'title == "OCR 引擎配置无效"',
        "rejected OCR action rewrote saved PDIC/PPP",
        "rejected OCR action changed the active project/page",
        "rejected OCR action changed unsaved PDIC/PPP in memory",
        "original_entry_snapshot",
        "original_polygon_snapshot",
        "ordinary GUI action failed OCR-free left_edge routing",
        'dispatched == [([0], "left_edge", False, False, False)]',
        'app.quick_bool_vars[name].set(value)',
        "app.sync_quick_settings()",
    ):
        assert required in source, required


def test_no_ocr_inference_claim_and_six_matrix_invocations_unchanged():
    source = (ROOT / "scripts/gui_project_roundtrip_smoke.py").read_text(encoding="utf-8")
    doc = (ROOT / "docs/architecture/REAL_SCAN_ACCEPTANCE_GATE_20261025.md").read_text(
        encoding="utf-8",
    )
    assert "MANUAL GATE OPEN / NOT PASSED" in doc
    assert "Round 64" in doc
    assert "call-recording spy" in doc
    assert "no real" in doc
    assert "OCR inference" in doc
    # Round 66: completion must not depend on a shared status label that
    # project settings autosave can overwrite after the actual crop callback.
    assert 'and app.batch_progress_var.get() == 100.0' in source
    assert 'and "已导出" in app.status_var.get()' not in source
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert workflow.count("scripts/gui_project_roundtrip_smoke.py") == 4
    assert workflow.count("Managed project PDIC/PPP Tk save-reopen") == 4
