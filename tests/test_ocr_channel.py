from __future__ import annotations

from pathlib import Path

from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.ocr_channel import (
    OcrChannelCandidate,
    OcrChannelSession,
    OcrTextChoice,
    choose_ocr_text,
    resolve_ocr_channel_plan,
)


def test_channel_plan_uses_existing_multi_engine_switches():
    settings = AppSettings(
        paddle_use_paddleocr=True,
        paddle_compare_tesseract=True,
        paddle_enable_lens=True,
        paddle_lens_mode="full",
    )

    plan = resolve_ocr_channel_plan(settings)

    assert plan.enabled_engines == ("paddle", "tesseract", "lens")
    assert plan.voting_engines == ("paddle", "tesseract", "lens")
    assert plan.lens_mode == "full"


def test_diagnostic_lens_runs_but_does_not_vote():
    settings = AppSettings(
        paddle_use_paddleocr=True,
        paddle_compare_tesseract=False,
        paddle_enable_lens=True,
        paddle_lens_mode="diagnostic",
    )

    plan = resolve_ocr_channel_plan(settings)

    assert plan.enabled_engines == ("paddle", "lens")
    assert plan.voting_engines == ("paddle",)


def test_single_engine_setting_is_only_fallback_when_channel_switches_are_off():
    settings = AppSettings(
        paddle_use_paddleocr=False,
        paddle_compare_tesseract=False,
        paddle_tesseract_rescue=False,
        paddle_enable_lens=False,
        paddle_lens_mode="off",
        ocr_engine="tesseract",
    )

    plan = resolve_ocr_channel_plan(settings)

    assert plan.enabled_engines == ("tesseract",)
    assert plan.voting_engines == ("tesseract",)


def test_one_crop_can_run_paddle_and_tesseract_together():
    settings = AppSettings(
        paddle_use_paddleocr=True,
        paddle_compare_tesseract=True,
        paddle_enable_lens=False,
    )

    session = OcrChannelSession(
        settings,
        paddle_runner=lambda image: OcrChannelCandidate(
            engine="paddle", text="Alpha", confidence=0.91,
        ),
        tesseract_runner=lambda image, psm: OcrChannelCandidate(
            engine="tesseract", text="alpha", confidence=0.80,
        ),
    )
    result = session.recognize_crop(Image.new("RGB", (100, 40), "white"))

    assert tuple(item.engine for item in result.candidates) == ("paddle", "tesseract")
    selected, agreed = choose_ocr_text(
        result.plan,
        [
            OcrTextChoice(item.engine, item.text, item.confidence)
            for item in result.candidates
            if item.ok
        ],
    )
    assert agreed is True
    assert selected is not None
    assert selected.engine == "paddle"
    assert selected.text == "Alpha"


def test_conflict_mode_calls_lens_only_when_local_ocr_conflicts():
    settings = AppSettings(
        paddle_use_paddleocr=True,
        paddle_compare_tesseract=True,
        paddle_enable_lens=True,
        paddle_lens_mode="conflict",
    )

    session = OcrChannelSession(
        settings,
        paddle_runner=lambda image: OcrChannelCandidate(engine="paddle", text="alpha"),
        tesseract_runner=lambda image, psm: OcrChannelCandidate(engine="tesseract", text="beta"),
        lens_runner=lambda image: OcrChannelCandidate(engine="lens", text="beta", confidence=0.82),
    )
    result = session.recognize_crop(Image.new("RGB", (100, 40), "white"))

    assert result.lens_attempted is True
    assert tuple(item.engine for item in result.candidates) == (
        "paddle", "tesseract", "lens",
    )
    selected, agreed = choose_ocr_text(
        result.plan,
        [OcrTextChoice(item.engine, item.text, item.confidence) for item in result.successful],
    )
    assert agreed is True
    assert selected is not None
    assert selected.engine == "tesseract"
    assert selected.text == "beta"


def test_diagnostic_lens_cannot_override_normal_ocr_text():
    settings = AppSettings(
        paddle_use_paddleocr=True,
        paddle_compare_tesseract=False,
        paddle_enable_lens=True,
        paddle_lens_mode="diagnostic",
    )
    session = OcrChannelSession(
        settings,
        paddle_runner=lambda image: OcrChannelCandidate(engine="paddle", text="alpha"),
        lens_runner=lambda image: OcrChannelCandidate(engine="lens", text="beta"),
    )
    result = session.recognize_crop(Image.new("RGB", (100, 40), "white"))

    selected, agreed = choose_ocr_text(
        result.plan,
        [OcrTextChoice(item.engine, item.text, item.confidence) for item in result.successful],
    )
    assert agreed is False
    assert selected is not None
    assert selected.engine == "paddle"


def test_marker_only_ocr_is_a_channel_consumer_not_single_engine_dispatch():
    import picture_capture.entry_classification_runtime as runtime

    source = Path(runtime.__file__).read_text(encoding="utf-8")
    assert "OcrChannelSession" in source
    assert "channel.recognize_crop(" in source
    assert "choose_ocr_text(" in source
    assert 'engine_name == "paddleocr"' not in source
    assert "OcrChannelCandidate(" not in source


def test_ocr_boundary_detection_is_a_separate_channel_consumer():
    import picture_capture.ocr_boundary_detection as boundary

    source = Path(boundary.__file__).read_text(encoding="utf-8")
    assert "resolve_ocr_channel_plan" in source
    assert "detect_ocr_headword_boundaries" in source
    assert "legacy_detect" in source


def test_historical_paddle_headword_entrypoint_remains_boundary_consumer_alias():
    import picture_capture.paddle_headwords as public

    assert public.detect_paddle_headwords is public.detect_ocr_headword_boundaries


def test_main_ui_presents_engine_selection_as_shared_ocr_channel():
    from picture_capture.ui_terminology import normalize_ui_text

    assert normalize_ui_text("三、融合 / OCR画线参数") == "三、OCR通道 / OCR画线"
    assert normalize_ui_text("三、OCR画线参数（默认）") == "三、OCR通道 / OCR画线"
    help_text = normalize_ui_text(
        "默认只启用 PaddleOCR；Tesseract 与 Google Lens 按需手动开启"
    )
    assert "共享 OCR 通道" in help_text
    assert "【仅OCR】与【OCR画线】共用" in help_text
