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
from picture_capture.ocr_channel_legacy import (
    apply_channel_plan_to_legacy_boundary_settings,
    route_legacy_boundary_ocr_through_channel,
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


def test_paddle_language_ignores_tesseract_specific_override():
    from picture_capture.ocr_channel import _paddle_language

    settings = AppSettings(
        ocr_language="spa+eng",
        tesseract_language="fra",
        paddle_language="",
    )

    assert _paddle_language(settings) == "es"


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


def test_shared_channel_owns_active_ocr_execution_not_legacy_parser():
    import picture_capture.ocr_channel as channel

    source = Path(channel.__file__).read_text(encoding="utf-8")
    assert "def run_paddle_raw(" in source
    assert "def run_tesseract_records(" in source
    assert "def run_lens_records(" in source
    assert "from .paddle_headwords" not in source
    assert "from . import paddle_headwords_core" not in source
    assert "import paddle_headwords_core" not in source


def test_marker_only_ocr_is_a_channel_consumer_not_single_engine_dispatch():
    import picture_capture.processing_core as processing_core

    source = Path(processing_core.__file__).read_text(encoding="utf-8")
    assert "OcrChannelSession" in source
    assert "channel.recognize_crop(" in source
    assert "choose_ocr_text(" in source
    assert 'engine_name == "paddleocr"' not in source
    assert "OcrChannelCandidate(" not in source


def test_ocr_boundary_detection_is_channel_neutral_consumer():
    import picture_capture.ocr_boundary_detection as boundary

    source = Path(boundary.__file__).read_text(encoding="utf-8")
    assert "apply_channel_plan_to_legacy_boundary_settings" in source
    assert "route_legacy_boundary_ocr_through_channel" in source
    assert "detect_ocr_headword_boundaries" in source
    assert "legacy_detect" in source
    assert "resolve_ocr_channel_plan" not in source
    for legacy_flag in (
        "paddle_use_paddleocr",
        "paddle_compare_tesseract",
        "paddle_enable_lens",
        "paddle_lens_mode",
    ):
        assert legacy_flag not in source


def test_legacy_boundary_adapter_translates_tesseract_fallback():
    settings = AppSettings(
        paddle_use_paddleocr=False,
        paddle_compare_tesseract=False,
        paddle_tesseract_rescue=False,
        paddle_enable_lens=False,
        paddle_lens_mode="off",
        ocr_engine="tesseract",
    )

    routed = apply_channel_plan_to_legacy_boundary_settings(settings)

    assert routed.paddle_use_paddleocr is False
    assert routed.paddle_compare_tesseract is True
    assert routed.paddle_tesseract_rescue is False
    assert routed.paddle_enable_lens is False
    assert routed.paddle_lens_mode == "off"
    assert settings.paddle_compare_tesseract is False


def test_legacy_boundary_runner_bridge_is_scoped_and_restores_core():
    from picture_capture import paddle_headwords_core as core

    settings = AppSettings(
        paddle_use_paddleocr=True,
        paddle_compare_tesseract=True,
        paddle_enable_lens=True,
        paddle_lens_mode="diagnostic",
    )
    original = (
        core.get_paddle_engine,
        core.run_paddle_band,
        core.run_tesseract_band_records,
        core.run_google_lens,
    )

    with route_legacy_boundary_ocr_through_channel(settings):
        active = (
            core.get_paddle_engine,
            core.run_paddle_band,
            core.run_tesseract_band_records,
            core.run_google_lens,
        )
        assert all(after is not before for before, after in zip(original, active))

    restored = (
        core.get_paddle_engine,
        core.run_paddle_band,
        core.run_tesseract_band_records,
        core.run_google_lens,
    )
    assert restored == original


def test_legacy_boundary_runner_bridge_respects_existing_monkeypatch(monkeypatch):
    from picture_capture import paddle_headwords_core as core

    def external_runner(*args, **kwargs):
        return [], "external"

    monkeypatch.setattr(core, "run_tesseract_band_records", external_runner)
    settings = AppSettings(
        paddle_use_paddleocr=False,
        paddle_compare_tesseract=True,
        paddle_enable_lens=False,
    )

    with route_legacy_boundary_ocr_through_channel(settings):
        assert core.run_tesseract_band_records is external_runner

    assert core.run_tesseract_band_records is external_runner


def test_historical_paddle_headword_entrypoint_remains_boundary_consumer_alias():
    import picture_capture.paddle_headwords as public

    assert public.detect_paddle_headwords is public.detect_ocr_headword_boundaries


def test_main_ui_presents_engine_selection_as_shared_ocr_channel():
    from picture_capture.ui_terminology import normalize_ui_text

    assert normalize_ui_text("三、融合 / OCR画线参数") == "三、共享 OCR 通道 / OCR画线"
    assert normalize_ui_text("三、OCR画线参数（默认）") == "三、共享 OCR 通道 / OCR画线"
    help_text = normalize_ui_text(
        "默认只启用 PaddleOCR；Tesseract 与 Google Lens 按需手动开启"
    )
    assert "共享 OCR 通道" in help_text
    assert "可同时启用" in help_text
    assert "【仅OCR】与【OCR画线】共用" in help_text


def test_marker_only_ui_copy_states_shared_multi_ocr_without_geometry_changes():
    from picture_capture.ui_terminology import normalize_ui_text

    text = normalize_ui_text(
        "仅OCR：只对已有画线做局部 PaddleOCR 补文字，不新增、删除或移动 marker。"
    )

    assert "共享 OCR 通道" in text
    assert "可同时使用多个 OCR" in text
    assert "不新增、删除或移动 marker" in text
    assert "局部 PaddleOCR" not in text
