from __future__ import annotations

import importlib.util
from pathlib import Path

GUARD_PATH = Path(__file__).resolve().parents[1] / "scripts" / "change_architecture_guard.py"
spec = importlib.util.spec_from_file_location("change_architecture_guard", GUARD_PATH)
assert spec is not None and spec.loader is not None
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
violations_in_source = guard.violations_in_source


def check(source: str) -> list[str]:
    return violations_in_source(source, "new_module.py")


def test_new_module_allows_explicit_runtime_dependency_injection():
    source = """
def make_controller(app, service):
    return service(app.settings)
"""
    assert check(source) == []


def test_new_module_rejects_shell_imports():
    assert any("GUI shell" in err for err in check("from picture_capture.app import PictureCaptureApp"))
    assert any("GUI shell" in err for err in check("from .app import ReviewWindow"))
    assert any("GUI shell" in err for err in check("import picture_capture.app"))


def test_new_module_rejects_import_time_installers():
    assert any("module-level setattr" in err for err in check("setattr(AppClass, 'method', replacement)"))
    assert any("module-level install_" in err for err in check("install_runtime_patches()"))
    assert check("def configure():\n    setattr(widget, 'title', 'demo')") == []


def test_new_module_rejects_invalid_python():
    assert any("invalid Python" in err for err in check("def broken(: pass"))
