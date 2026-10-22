"""Issue #562: one OCR supervised fusion owner, no root implementation shim."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import picture_capture.paddle_headwords as public
import picture_capture.paddle_headwords_core as core
from picture_capture.ocr import evidence_fusion as fusion


def test_supervised_fusion_is_physically_owned_by_ocr() -> None:
    root = Path(fusion.__file__).resolve().parents[1]
    assert Path(fusion.__file__).resolve() == root / "ocr" / "evidence_fusion.py"
    assert not (root / "evidence_fusion.py").exists()
    assert importlib.util.find_spec("picture_capture.evidence_fusion") is None


def test_historical_paddle_facade_keeps_same_supervised_implementation() -> None:
    assert public._fusion is fusion
    assert public.filter_headword_records is fusion.filter_headword_records
    assert public.OCRRecord is core.OCRRecord
    assert public.HeadwordFilterRule is core.HeadwordFilterRule
    # The core must keep its own implementations: supervised behavior is
    # provided via explicit injected callbacks, not import-time mutation.
    assert core.filter_headword_records is not fusion.filter_headword_records
