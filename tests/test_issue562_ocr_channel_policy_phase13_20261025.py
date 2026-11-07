"""Issue #562: OCR engine-selection policy is owned by ocr/channel_policy."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

from picture_capture import ocr_channel
from picture_capture.models import AppSettings
from picture_capture.ocr import channel_policy


ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def _disabled(**overrides):
    return AppSettings(
        paddle_use_paddleocr=False,
        paddle_compare_tesseract=False,
        paddle_tesseract_rescue=False,
        paddle_enable_lens=False,
        paddle_lens_mode="off",
        **overrides,
    )


def test_ocr_policy_physical_owner_and_stable_public_plan_identity():
    root = ast.parse((ROOT / "ocr_channel.py").read_text(encoding="utf-8"))
    owner = ast.parse((ROOT / "ocr/channel_policy.py").read_text(encoding="utf-8"))
    root_fn = next(n for n in root.body if isinstance(n, ast.FunctionDef)
                   and n.name == "resolve_ocr_channel_plan")
    owner_fn = next(n for n in owner.body if isinstance(n, ast.FunctionDef)
                    and n.name == "resolve_plan")
    assert len(root_fn.body) == 2
    assert len(owner_fn.body) >= 8
    assert list(inspect.signature(ocr_channel.resolve_ocr_channel_plan).parameters) == ["settings"]
    assert ocr_channel.resolve_ocr_channel_plan.__module__ == "picture_capture.ocr_channel"
    plan = ocr_channel.resolve_ocr_channel_plan(AppSettings())
    assert type(plan) is ocr_channel.OcrChannelPlan
    assert plan.__class__.__module__ == "picture_capture.ocr_channel"
    assert channel_policy.resolve_plan is not ocr_channel.resolve_ocr_channel_plan


def test_ocr_policy_legacy_fallback_lens_and_invalid_modes():
    lens = _disabled(ocr_engine="google_lens")
    plan = ocr_channel.resolve_ocr_channel_plan(lens)
    assert plan.enabled_engines == ("lens",)
    assert plan.voting_engines == ("lens",)
    assert plan.lens_mode == "full"

    unknown = _disabled(ocr_engine="not-an-engine")
    plan = ocr_channel.resolve_ocr_channel_plan(unknown)
    assert plan.enabled_engines == ("tesseract",)
    assert plan.voting_engines == ("tesseract",)

    settings = AppSettings(
        paddle_use_paddleocr=True, paddle_compare_tesseract=False,
        paddle_enable_lens=True, paddle_lens_mode="not-a-mode",
    )
    plan = ocr_channel.resolve_ocr_channel_plan(settings)
    assert plan.enabled_engines == ("paddle", "lens")
    assert plan.voting_engines == ("paddle", "lens")
    assert plan.lens_mode == "conflict"


def test_ocr_policy_rescue_diagnostic_voting_and_live_monkeypatch(monkeypatch):
    settings = AppSettings(
        paddle_use_paddleocr=True, paddle_compare_tesseract=False,
        paddle_tesseract_rescue=True, paddle_enable_lens=True,
        paddle_lens_mode="diagnostic",
    )
    plan = ocr_channel.resolve_ocr_channel_plan(settings)
    assert plan.enabled_engines == ("paddle", "tesseract", "lens")
    assert plan.voting_engines == ("paddle", "tesseract")
    assert plan.lens_mode == "diagnostic"

    calls = []
    monkeypatch.setattr(ocr_channel, "_normalized_engine_name",
                        lambda name: (calls.append(name) or "paddle"))
    monkeypatch.setattr(ocr_channel, "OCR_ENGINE_ORDER",
                        ("lens", "tesseract", "paddle"))
    monkeypatch.setattr(ocr_channel, "OcrChannelPlan",
                        lambda **kwargs: SimpleNamespace(**kwargs))
    fallback = ocr_channel.resolve_ocr_channel_plan(_disabled(ocr_engine="custom"))
    assert calls == ["custom"]
    assert isinstance(fallback, SimpleNamespace)
    assert fallback.enabled_engines == ("paddle",)

    reordered = ocr_channel.resolve_ocr_channel_plan(settings)
    assert reordered.enabled_engines == ("lens", "tesseract", "paddle")
    assert reordered.voting_engines == ("tesseract", "paddle")
