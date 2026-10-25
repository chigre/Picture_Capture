"""Issue #562 phase 16: root OCR core is truly retired, with stable old imports."""
from __future__ import annotations

import importlib
import pickle
import subprocess
import sys
from pathlib import Path

from picture_capture import paddle_headwords as public
from picture_capture.ocr import headword_core_runtime as canonical


def test_root_core_is_absent_and_legacy_import_is_the_real_canonical_module():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert not (pkg / "paddle_headwords_core.py").exists()
    old = importlib.import_module("picture_capture.paddle_headwords_core")
    assert old is canonical
    assert old.__dict__ is canonical.__dict__
    assert old.__file__.endswith("ocr/headword_core_runtime.py")


def test_legacy_callable_identity_and_import_paths_survive():
    legacy = importlib.import_module("picture_capture.paddle_headwords_core")
    for name in ("parse_headword_text", "extract_ocr_records", "_json_payload", "detect_paddle_headwords"):
        obj = getattr(legacy, name)
        assert obj.__module__ == "picture_capture.paddle_headwords_core"
        assert getattr(canonical, name) is obj
        assert getattr(public, name, None) is not None
        assert pickle.loads(pickle.dumps(obj)) is obj


def test_public_assignment_mirror_reaches_exact_canonical_globals(monkeypatch):
    old = importlib.import_module("picture_capture.paddle_headwords_core")
    original = old._json_payload
    sentinel = lambda result: {"rec_texts": ["patched"], "rec_scores": [0.9], "rec_boxes": [[1, 1, 8, 8]]}
    monkeypatch.setattr(public, "_json_payload", sentinel)
    assert old._json_payload is sentinel
    assert canonical._json_payload is sentinel
    monkeypatch.setattr(public, "_json_payload", original)


def test_lazy_compat_alias_does_not_initialize_ocr_during_package_import():
    script = (
        "import sys, picture_capture; "
        "assert 'picture_capture.ocr.headword_core_runtime' not in sys.modules; "
        "import picture_capture.paddle_headwords_core as alias; "
        "from picture_capture.ocr import headword_core_runtime as owner; "
        "assert alias is owner"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
