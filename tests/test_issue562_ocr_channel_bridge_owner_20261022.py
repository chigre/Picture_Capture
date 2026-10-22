"""#562 OCR boundary/channel bridge: canonical owner and scoped legacy runner contract."""
from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path

import pytest

from picture_capture.models import AppSettings
from picture_capture.ocr import channel_legacy

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "picture_capture"
RUNNERS = (
    "get_paddle_engine",
    "run_paddle_band",
    "run_tesseract_band_records",
    "run_google_lens",
)


def test_channel_bridge_is_physically_owned_by_ocr_without_retired_shim():
    assert (PACKAGE / "ocr" / "channel_legacy.py").is_file()
    assert not (PACKAGE / "ocr_channel_legacy.py").exists()
    assert importlib.util.find_spec("picture_capture.ocr_channel_legacy") is None
    assert importlib.import_module("picture_capture.ocr.channel_legacy") is channel_legacy
    assert "picture_capture.ocr.channel_legacy" in (
        PACKAGE / "ocr" / "boundary_detection.py"
    ).read_text(encoding="utf-8")


def test_bridge_restores_original_runners_on_exception_and_nested_scope():
    from picture_capture import paddle_headwords_core as core

    snapshot = tuple(getattr(core, key) for key in RUNNERS)
    settings = AppSettings(
        paddle_use_paddleocr=True,
        paddle_compare_tesseract=True,
        paddle_enable_lens=True,
        paddle_lens_mode="diagnostic",
    )

    with pytest.raises(RuntimeError, match="intentional"):
        with channel_legacy.route_legacy_boundary_ocr_through_channel(settings):
            outer = tuple(getattr(core, key) for key in RUNNERS)
            assert all(current is not before for current, before in zip(outer, snapshot))
            with channel_legacy.route_legacy_boundary_ocr_through_channel(settings):
                assert tuple(getattr(core, key) for key in RUNNERS) == outer
            assert tuple(getattr(core, key) for key in RUNNERS) == outer
            raise RuntimeError("intentional")

    assert tuple(getattr(core, key) for key in RUNNERS) == snapshot


def test_retired_ocr_channel_bridge_path_has_no_source_or_test_imports():
    for parent in (ROOT / "src", ROOT / "tests", ROOT / "scripts"):
        for path in parent.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    assert not any(
                        alias.name == "picture_capture.ocr_channel_legacy"
                        for alias in node.names
                    ), (path, node.lineno)
                elif isinstance(node, ast.ImportFrom):
                    assert node.module != "picture_capture.ocr_channel_legacy", (
                        path, node.lineno
                    )
                    if node.module == "picture_capture":
                        assert not any(
                            alias.name == "ocr_channel_legacy" for alias in node.names
                        ), (path, node.lineno)
                    if node.module == "ocr_channel_legacy" and node.level:
                        assert False, (path, node.lineno)
