"""Issue #562 phase 16: full OCR core runtime migrated without public API loss."""
from __future__ import annotations

import importlib
import pickle
import subprocess
import sys
from pathlib import Path

from picture_capture import paddle_headwords as public
from picture_capture.ocr import headword_core_runtime as canonical


def test_root_compat_bridge_is_minimal_and_runtime_has_one_canonical_owner():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    bridge = (pkg / "paddle_headwords_core.py").read_text(encoding="utf-8")
    assert "_sys.modules[__name__] = _canonical" in bridge
    assert "def " not in bridge
    assert "class " not in bridge
    old = importlib.import_module("picture_capture.paddle_headwords_core")
    assert old is canonical
    assert old.__dict__ is canonical.__dict__
    assert Path(old.__file__).resolve() == pkg / "ocr/headword_core_runtime.py"


def test_legacy_callable_identity_and_pickle_import_paths_survive():
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


def test_package_import_is_metadata_only_and_legacy_import_is_lazy():
    script = (
        "import sys, picture_capture; "
        "assert [n for n in sys.modules if n.startswith('picture_capture.')] == []; "
        "import picture_capture.paddle_headwords_core as alias; "
        "from picture_capture.ocr import headword_core_runtime as owner; "
        "assert alias is owner"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
