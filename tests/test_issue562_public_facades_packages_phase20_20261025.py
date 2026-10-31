"""Phase 20: public OCR/processing facades remain exact package modules."""
from __future__ import annotations
import importlib
import pickle
import subprocess
import sys
from pathlib import Path

def test_facades_retired_from_root_and_public_names_are_same():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture"
    for name in ("processing", "paddle_headwords"):
        assert not (root / (name + ".py")).exists()
        path = root / name / "__init__.py"
        assert path.is_file()
        source = path.read_text(encoding="utf-8")
        assert "publish_core_namespace(globals(), _core)" in source
        assert "install_core_assignment_mirror(__name__, _core)" in source
        facade = importlib.import_module("picture_capture." + name)
        assert facade.__name__ == "picture_capture." + name
        assert Path(facade.__file__).resolve() == path.resolve()

def test_both_facades_still_mirror_monkeypatches_and_pickle_spawn_functions(monkeypatch):
    from picture_capture import processing, paddle_headwords
    from picture_capture import processing_core, paddle_headwords_core
    for facade, core, hook in (
        (processing, processing_core, "_source_px"),
        (paddle_headwords, paddle_headwords_core, "_json_payload"),
    ):
        original = getattr(core, hook)
        marker = lambda *args, **kwargs: "patched"
        monkeypatch.setattr(facade, hook, marker)
        assert getattr(core, hook) is marker
        monkeypatch.setattr(facade, hook, original)
    assert pickle.loads(pickle.dumps(processing.detect_entries_job)) is processing.detect_entries_job
    assert pickle.loads(pickle.dumps(paddle_headwords_core.detect_paddle_headwords)) is paddle_headwords_core.detect_paddle_headwords

def test_bare_package_import_stays_metadata_only():
    script = (
        "import sys,picture_capture;"
        "assert not [k for k in sys.modules if k.startswith('picture_capture.')];"
        "from picture_capture import processing,paddle_headwords;"
        "assert processing.__name__=='picture_capture.processing';"
        "assert paddle_headwords.__name__=='picture_capture.paddle_headwords';"
        "assert callable(processing.detect_entries);"
        "assert callable(paddle_headwords.detect_paddle_headwords)"
    )
    result = subprocess.run([sys.executable,"-c",script],capture_output=True,text=True)
    assert result.returncode == 0, result.stdout+result.stderr
