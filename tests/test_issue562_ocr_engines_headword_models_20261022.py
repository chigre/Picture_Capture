"""Issue #562: OCR engine and headword-model leaves are truly package-owned."""
from __future__ import annotations

import ast
import importlib.util
import pickle
from pathlib import Path

import picture_capture.paddle_headwords as public_headwords
import picture_capture.paddle_headwords_core as core
from picture_capture.ocr import headword_models
from picture_capture.ocr.engines import find_tesseract, lens_status, tesseract_status

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "picture_capture"
MOVED = {
    "ocr_engines": "ocr/engines.py",
    "paddle_headword_models": "ocr/headword_models.py",
}


def test_ocr_leaves_are_physical_and_old_root_modules_absent():
    for old_name, new_path in MOVED.items():
        assert not (PACKAGE / (old_name + ".py")).exists()
        assert (PACKAGE / new_path).is_file()
        assert importlib.util.find_spec("picture_capture." + old_name) is None
    assert callable(find_tesseract)
    assert callable(lens_status)
    assert callable(tesseract_status)


def test_headword_data_model_pickle_and_historical_facade_identity():
    for name in ("OCRRecord", "OCRLine", "GrammarTailParse", "HeadwordParse", "HeadwordFilterRule"):
        model = getattr(headword_models, name)
        assert getattr(core, name) is model
        assert getattr(public_headwords, name) is model
        assert model.__module__ == "picture_capture.paddle_headwords_core"
        assert pickle.loads(pickle.dumps(model)) is model


def test_no_old_ocr_module_imports_in_python_sources_tests_or_scripts():
    for folder in ("src", "tests", "scripts"):
        for path in (ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name not in {"picture_capture." + old for old in MOVED}, (path, node.lineno)
                elif isinstance(node, ast.ImportFrom):
                    target = node.module or ""
                    assert target not in {"picture_capture." + old for old in MOVED}, (path, node.lineno)
                    if node.level and target in MOVED:
                        raise AssertionError((path, node.lineno, target))
                    if target in ("", "picture_capture"):
                        assert not any(alias.name in MOVED for alias in node.names), (path, node.lineno)
