"""Issue #562 phase 19: retired root compatibility files preserve ABI."""
from __future__ import annotations
import importlib
import pickle
import subprocess
import sys
from pathlib import Path

def test_legacy_packages_are_single_live_core_modules():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture"
    for stem, owner, path in [
        ("processing_core", "picture_capture.runtime.processing_core_runtime", "runtime/processing_core_runtime.py"),
        ("paddle_headwords_core", "picture_capture.ocr.headword_core_runtime", "ocr/headword_core_runtime.py"),
    ]:
        assert not (root / (stem + ".py")).exists()
        bridge = root / stem / "__init__.py"
        assert bridge.is_file()
        assert "_sys.modules[__name__] = _canonical" in bridge.read_text(encoding="utf-8")
        legacy = importlib.import_module("picture_capture." + stem)
        canonical = importlib.import_module(owner)
        assert legacy is canonical
        assert legacy.__dict__ is canonical.__dict__
        assert Path(legacy.__file__).resolve() == (root / path).resolve()

def test_spawn_pickle_imports_and_patching_same_globals(monkeypatch):
    from picture_capture import processing, paddle_headwords
    core = importlib.import_module("picture_capture.processing_core")
    ocr = importlib.import_module("picture_capture.paddle_headwords_core")
    for fn in (core.detect_entries_job, core.split_illustrations_job, ocr.detect_paddle_headwords, ocr._json_payload):
        assert pickle.loads(pickle.dumps(fn)) is fn
    orig = core._source_px
    monkeypatch.setattr(processing, "_source_px", lambda x: 81)
    assert core._source_px(7) == 81
    monkeypatch.setattr(processing, "_source_px", orig)
    orig_ocr = ocr._json_payload
    sentinel = object()
    monkeypatch.setattr(paddle_headwords, "_json_payload", sentinel)
    assert ocr._json_payload is sentinel
    monkeypatch.setattr(paddle_headwords, "_json_payload", orig_ocr)

def test_bare_package_has_no_eager_loading():
    cmd = (
        "import picture_capture,sys;"
        "assert not [x for x in sys.modules if x.startswith('picture_capture.')];"
        "import picture_capture.processing_core as legacy_proc;"
        "import picture_capture.paddle_headwords_core as legacy_ocr;"
        "from picture_capture.runtime import processing_core_runtime;"
        "from picture_capture.ocr import headword_core_runtime;"
        "assert legacy_proc is processing_core_runtime;"
        "assert legacy_ocr is headword_core_runtime"
    )
    result = subprocess.run([sys.executable,"-c",cmd],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr + result.stdout
