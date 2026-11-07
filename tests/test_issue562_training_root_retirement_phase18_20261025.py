"""Issue #562 Phase 18: remove root training exporter with single-module ABI."""
from __future__ import annotations

import importlib
import inspect
import json
import pickle
import subprocess
import sys
from pathlib import Path

from picture_capture.training import export_runtime as owner
from picture_capture.training import manifest_v2, zip_publish


def test_no_root_python_exporter_and_legacy_package_shares_exact_state():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert not (pkg / "training_export.py").exists()
    assert (pkg / "training_export" / "__init__.py").is_file()
    assert (pkg / "training" / "export_runtime.py").is_file()
    public = importlib.import_module("picture_capture.training_export")
    assert public is owner
    assert public.__dict__ is owner.__dict__
    assert Path(public.__file__).resolve() == (pkg / "training" / "export_runtime.py").resolve()
    assert public.TrainingExportCancelled is zip_publish.TrainingExportCancelled
    assert public.make_training_zip is zip_publish.make_training_zip
    assert public.write_training_manifest is manifest_v2.write_training_manifest


def test_legacy_pickle_and_runtime_patch_still_target_real_owner(monkeypatch, tmp_path):
    public = importlib.import_module("picture_capture.training_export")
    for name in ("_read_json", "_copy_if_exists", "export_training_page"):
        fn = getattr(public, name)
        assert getattr(owner, name) is fn
        assert fn.__module__ == "picture_capture.training_export"
        assert pickle.loads(pickle.dumps(fn)) is fn
    marker = object()
    observed = {}
    def export_stub(page, project_root, settings, staging_root, page_index, *, deps):
        observed.update(deps)
        return {"marker": marker, "page_index": page_index}
    monkeypatch.setattr(public._page_v2, "export_training_page", export_stub)
    stub_result = public.export_training_page(
        tmp_path / "a.png", tmp_path, None, tmp_path, 3
    )
    assert stub_result["marker"] is marker and stub_result["page_index"] == 3
    assert observed["read_pdic"] is public.read_pdic
    assert observed["derive_geometry"] is public.derive_geometry
    monkeypatch.setattr(public, "read_pdic", lambda _: ["patched"])
    public.export_training_page(tmp_path / "a.png", tmp_path, None, tmp_path, 3)
    assert observed["read_pdic"](None) == ["patched"]


def test_json_and_file_copy_helpers_preserve_lossless_behavior(tmp_path):
    public = importlib.import_module("picture_capture.training_export")
    path = tmp_path / "项目.json"
    assert public._read_json(path) == {}
    path.write_text("[]", encoding="utf-8")
    assert public._read_json(path) == {}
    path.write_text('{"中文": "ABC"}', encoding="utf-8")
    assert public._read_json(path) == {"中文": "ABC"}
    copied = tmp_path / "out" / "词条.txt"
    original = tmp_path / "词条.txt"
    original.write_bytes(b"\xef\xbb\xbfhello\r\n")
    assert public._copy_if_exists(original, copied) == copied.as_posix()
    assert copied.read_bytes() == original.read_bytes()
    assert public._copy_if_exists(tmp_path / "missing", copied) is None


def test_bare_package_has_no_training_side_effect_and_subprocess_imports_work():
    script = (
        "import sys, picture_capture;"
        "assert not [k for k in sys.modules if k.startswith('picture_capture.')];"
        "import picture_capture.training_export as old;"
        "from picture_capture.training import export_runtime as current;"
        "assert old is current;"
        "assert old.make_training_zip.__module__ == 'picture_capture.training_export'"
    )
    p = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr + p.stdout
