"""Issue #562: full oversized CJK local-recovery and Y-refinement owner."""
from __future__ import annotations

from dataclasses import fields
import subprocess
import sys

import numpy as np
from PIL import Image

from picture_capture import paddle_headwords_core as core
from picture_capture.ocr import cjk_recovery as owner
from picture_capture.models import AppSettings
from picture_capture.ocr.headword_models import OCRRecord


def _record(text: str, box=(2, 20, 22, 40), *, recovery="", source=""):
    return OCRRecord(text, .94, box, recovery=recovery, recovery_source_text=source)


def test_leaf_import_is_isolated_from_heavy_ocr_engine_and_gui():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.ocr.cjk_recovery import CjkRecoveryDeps
assert 'picture_capture.paddle_headwords_core' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


def test_all_live_recovery_dependencies_include_verification_policy():
    names = {field.name for field in fields(owner.CjkRecoveryDeps)}
    assert len(names) == 22
    assert {"_robust_record_line_height", "_recover_oversized_cjk_ocr_records",
            "_recover_image_first_oversized_cjk_records", "refine_separator_y",
            "refine_separator_y_adaptive", "refine_first_content_y",
            "_cjk_visual_projection_runs", "_VERIFIED_OVERSIZED_CJK_RECOVERIES",
            "normalize_page_rgb", "run_paddle_band"} <= names
    deps = core._cjk_recovery_deps()
    assert deps.refine_separator_y is core.refine_separator_y
    assert deps._VERIFIED_OVERSIZED_CJK_RECOVERIES is core._VERIFIED_OVERSIZED_CJK_RECOVERIES


def test_robust_line_height_ignores_pathological_giant_box():
    settings = AppSettings()
    records = [
        _record("案", (0, 0, 15, 10)),
        _record("臺", (0, 10, 15, 22)),
        _record("大", (0, 22, 15, 300)),
    ]
    normal = core._robust_record_line_height(records, settings)
    assert 8.0 <= normal <= 12.0


def test_local_single_cjk_recovery_preserves_left_edge_gate(monkeypatch):
    monkeypatch.setattr(core, "parse_headword_text", lambda *a, **kw: None)
    monkeypatch.setattr(
        core, "_leading_cjk_ideograph",
        lambda text: "案" if text == "案1" else "",
    )
    records = [_record("案1", (5, 0, 25, 20)),
               _record("非", (60, 0, 80, 20))]
    word, conf, source = core._single_cjk_from_local_records(
        records, AppSettings(), object(), max_left_x=15)
    assert (word, conf, source) == ("案", .94, "案1")
    assert core._single_cjk_from_local_records(
        records, AppSettings(), object(), max_left_x=2
    ) == ("", 0., "")


def test_oversized_recovery_guards_do_not_trigger_for_non_chinese(monkeypatch):
    monkeypatch.setattr(core, "_is_chinese_ocr", lambda settings: False)
    records = [_record("alpha")]
    image = Image.new("RGB", (70, 100), "white")
    try:
        assert core._recover_oversized_cjk_ocr_records(
            records, image, AppSettings(), object()
        ) == (records, [])
        assert core._recover_image_first_oversized_cjk_records(
            records, image, AppSettings(), object()
        ) == (records, [])
    finally:
        image.close()


def test_verified_oversized_run_prevents_false_duplicate_recovery(monkeypatch):
    verified = _record(
        "案", (2, 20, 22, 40),
        recovery="image_first_oversized_local_ocr",
    )
    monkeypatch.setattr(core, "parse_headword_text", lambda *a, **kw: None)
    assert core._record_already_represents_oversized_run(
        verified, (20, 40), 24, AppSettings(), object())
    # Extremely tall raw boxes never satisfy the one-glyph physical gate.
    raw_giant = _record("案", (2, 0, 22, 100))
    assert not core._record_already_represents_oversized_run(
        raw_giant, (20, 40), 24, AppSettings(), object())


def test_suppresses_only_raw_observations_duplicated_by_verified_local_crop():
    verified = _record(
        "摆", (2, 20, 24, 42),
        recovery="image_first_oversized_local_ocr",
        source="摆1",
    )
    duplicate = _record("摆1", (0, 17, 28, 49))
    neighbor = _record("新词", (1, 62, 25, 82))
    initial = [duplicate, verified, neighbor]
    retained, audits = core._suppress_raw_records_shadowed_by_verified_cjk_recovery(initial)
    assert retained == [verified, neighbor]
    assert initial == [duplicate, verified, neighbor]  # raw observations untouched
    assert len(audits) == 1
    assert audits[0]["reason"] == "same_recovery_source_text"
    assert audits[0]["recovery"] == "image_first_oversized_local_ocr"
    assert core._suppress_raw_records_shadowed_by_verified_cjk_recovery(
        [duplicate, neighbor]) == ([duplicate, neighbor], [])


def test_separator_three_entrypoints_preserve_disabled_semantics():
    settings = AppSettings()
    settings.paddle_refine_separator_y = False
    gray = np.zeros((60, 70), dtype=np.uint8)
    y, diag = core.refine_separator_y(gray, 21, 13, settings)
    assert y == 21 and diag == {"enabled": False, "reason": "disabled"}
    y, diag = core.refine_separator_y_adaptive(gray, 21, 13, settings)
    assert y == 21 and diag["adaptive_mode"] == "off"
    y, diag = core.refine_first_content_y(gray, 21, 13, settings)
    assert y == 21 and diag == {"enabled": False, "reason": "disabled"}


def test_enabled_refiners_are_bounded_and_preserve_diagnostic_coordinates():
    settings = AppSettings()
    settings.paddle_refine_separator_y = True
    gray = np.full((95, 100), 255, dtype=np.uint8)
    gray[22:32, 3:70] = 0
    gray[48:60, 3:70] = 0
    for fn in (
        lambda: core.refine_separator_y(gray, 45, 15, settings),
        lambda: core.refine_separator_y_adaptive(
            gray, 45, 15, settings, content_top=48),
        lambda: core.refine_first_content_y(gray, 45, 15, settings),
    ):
        y, diag = fn()
        assert isinstance(y, int) and 0 <= y < 95
        assert isinstance(diag, dict)
        assert diag.get("enabled") is True
