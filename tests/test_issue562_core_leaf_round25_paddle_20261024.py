"""Round 25: Paddle engine/cache and OCR pixel inference ownership."""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path
from types import ModuleType

from PIL import Image

from picture_capture import paddle_headwords_core as core
from picture_capture.models import AppSettings
from picture_capture.ocr import paddle_engine_lifecycle


def test_exact_lifecycle_owner_and_original_core_signatures():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(pkg.glob("*.py"))) == 10
    path = pkg / "ocr" / "paddle_engine_lifecycle.py"
    assert path.is_file()
    assert not (pkg / path.name).exists()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert {n.name for n in tree.body if isinstance(n, ast.FunctionDef)} == {
        "clear_paddle_engine_cache_impl", "get_paddle_engine_impl", "run_paddle_band_impl",
    }
    assert not any(isinstance(n, (ast.Assign, ast.AnnAssign, ast.ClassDef)) for n in tree.body)
    assert list(inspect.signature(core.clear_paddle_engine_cache).parameters) == ["keep_key"]
    assert list(inspect.signature(core.get_paddle_engine).parameters) == ["settings"]
    assert list(inspect.signature(core.run_paddle_band).parameters) == ["band", "settings", "engine"]
    for name in ("clear_paddle_engine_cache", "get_paddle_engine", "run_paddle_band"):
        assert getattr(core, name).__module__ == "picture_capture.paddle_headwords_core"


def test_engine_cache_eviction_keeps_active_key(monkeypatch):
    keep = ("en", "cpu", "v4", False)
    drop = ("ch", "cpu", "v4", False)
    cache = {keep: object(), drop: object()}
    monkeypatch.setattr(core, "_ENGINE_CACHE", cache)
    core.clear_paddle_engine_cache(keep_key=keep)
    assert set(cache) == {keep}
    core.clear_paddle_engine_cache()
    assert cache == {}


def test_paddle_engine_lazy_creation_reuse_and_runtime_hooks(monkeypatch):
    from picture_capture.layout import detection as layout_detection
    from picture_capture.runtime import windows_gpu

    events = []
    fake_module = ModuleType("paddleocr")
    class FakePaddleOCR:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            events.append("initialized")
    fake_module.PaddleOCR = FakePaddleOCR
    monkeypatch.setitem(sys.modules, "paddleocr", fake_module)
    monkeypatch.setattr(layout_detection, "clear_text_detection_cache", lambda: events.append("clear_layout"))
    monkeypatch.setattr(windows_gpu, "configure_windows_nvidia_dlls", lambda: events.append("dlls"))
    monkeypatch.setattr(core, "_paddle_language", lambda settings: "en")
    monkeypatch.setattr(core, "resolve_paddle_device", lambda: "cpu")
    monkeypatch.setattr(core, "_ENGINE_CACHE", {})

    settings = AppSettings()
    first = core.get_paddle_engine(settings)
    second = core.get_paddle_engine(settings)
    assert first is second and isinstance(first, FakePaddleOCR)
    assert events == ["clear_layout", "dlls", "initialized"]
    assert first.kwargs["enable_mkldnn"] is False
    assert first.kwargs["lang"] == "en"
    assert len(core._ENGINE_CACHE) == 1


def test_raw_ocr_prediction_keeps_coordinates_and_score_gate():
    class Result:
        json = {"res": {"rec_texts": ["word"], "rec_scores": [.9],
                        "rec_boxes": [[100, 200, 300, 400]]}}
    class Engine:
        def predict(self, image, **kwargs):
            assert image.shape[:2] == (1400, 700)
            assert kwargs["text_rec_score_thresh"] == core._RAW_OCR_THRESHOLD
            assert kwargs["use_doc_unwarping"] is False
            return [Result()]
    band = Image.new("RGB", (1400, 2800), "white")
    got = core.run_paddle_band(band, AppSettings(paddle_max_input_side=1400), Engine())
    assert got == [core.OCRRecord("word", .9, (200, 400, 600, 800))]
