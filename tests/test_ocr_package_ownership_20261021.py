"""Issue #562: OCR implementation modules have physical package ownership."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
OWNERS = {
    "ocr_action_guard": "action_guard",
    "ocr_boundary_detection": "boundary_detection",
    "ocr_final_decisions": "final_decisions",
    "ocr_lazy_secondary": "lazy_secondary",
    "ocr_pdic_preservation": "pdic_preservation",
    "ocr_peer_style": "peer_style",
    "ocr_tesseract_runner": "tesseract_runner",
    "ocr_text_io": "text_io",
    "paddle_cache_storage": "paddle_cache_storage",
    "paddle_raw_cache_signature": "paddle_raw_cache_signature",
    "tesseract_raw_cache": "tesseract_raw_cache",
}


@pytest.mark.parametrize("old, owner", sorted(OWNERS.items()))
def test_ocr_owner_is_real_module_without_root_shim(old: str, owner: str) -> None:
    assert not (PKG / (old + ".py")).exists()
    assert (PKG / "ocr" / (owner + ".py")).is_file()
    assert importlib.util.find_spec("picture_capture." + old) is None
    assert importlib.util.find_spec("picture_capture.ocr." + owner) is not None


def test_ocr_package_init_has_no_eager_engine_initialization() -> None:
    source = (PKG / "ocr" / "__init__.py").read_text(encoding="utf-8")
    assert "paddleocr" not in source.lower()
    assert "from . import" not in source
