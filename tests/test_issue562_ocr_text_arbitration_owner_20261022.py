"""Issue #562: OCR-channel text voting has a pure package owner.

Public channel dataclasses and imports must remain stable for saved integrations;
the canonical algorithm must be shared with the historical OCR-channel facade.
"""
from __future__ import annotations

import importlib
import pickle
import subprocess
import sys
from pathlib import Path

from picture_capture import ocr_channel
from picture_capture.ocr import text_arbitration as text
from picture_capture.ocr_channel import OcrChannelPlan, OcrTextChoice


def _choice(engine: str, value: str) -> OcrTextChoice:
    return OcrTextChoice(engine=engine, text=value, confidence=0.8)


def test_text_arbitration_physical_owner_and_historical_identity() -> None:
    package = Path(ocr_channel.__file__).resolve().parent
    assert Path(text.__file__).resolve() == package / "ocr" / "text_arbitration.py"
    assert ocr_channel.channel_text_key is text.channel_text_key
    assert ocr_channel.choose_ocr_text is text.choose_ocr_text
    assert OcrTextChoice.__module__ == "picture_capture.ocr_channel"
    assert pickle.loads(pickle.dumps(_choice("paddle", "café"))) == _choice("paddle", "café")


def test_nfkc_agreement_preserves_priority_and_diagnostic_exclusion() -> None:
    plan = OcrChannelPlan(
        enabled_engines=("paddle", "tesseract", "lens"),
        voting_engines=("paddle", "tesseract"),
        lens_mode="diagnostic",
    )
    choices = [
        _choice("lens", "not a vote"),
        _choice("tesseract", "  A  B  "),
        _choice("paddle", "ａ b"),
    ]
    assert text.channel_text_key(choices[1].text) == text.channel_text_key(choices[2].text)
    assert text.choose_ocr_text(plan, choices) == (choices[2], True)
    assert text.choose_ocr_text(plan, [_choice("lens", "only diagnostic")]) == (None, False)


def test_disagreement_returns_first_voter_and_majority_tie_is_stable() -> None:
    plan = OcrChannelPlan(
        enabled_engines=("paddle", "tesseract", "lens"),
        voting_engines=("paddle", "tesseract", "lens"),
        lens_mode="full",
    )
    choices = [_choice("lens", "third"), _choice("tesseract", "second"), _choice("paddle", "first")]
    assert text.choose_ocr_text(plan, choices) == (choices[2], False)
    choices = [_choice("lens", "a"), _choice("paddle", "Ａ"), _choice("tesseract", "a")]
    assert text.choose_ocr_text(plan, choices) == (choices[1], True)


def test_leaf_import_before_channel_module_is_cycle_free() -> None:
    script = """
import importlib
import sys
leaf = importlib.import_module('picture_capture.ocr.text_arbitration')
assert 'picture_capture.ocr_channel' not in sys.modules
channel = importlib.import_module('picture_capture.ocr_channel')
assert channel.choose_ocr_text is leaf.choose_ocr_text
assert channel.channel_text_key is leaf.channel_text_key
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
