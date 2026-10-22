"""Issue #562: two physical platform runtime owners, without root compatibility shims."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.runtime import environment, windows_gpu

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


@pytest.mark.parametrize("former,owner,fn", [
    ("runtime_environment", "environment", "resolve_paddle_device"),
    ("windows_gpu", "windows_gpu", "configure_windows_nvidia_dlls"),
])
def test_canonical_platform_runtime_owner(former: str, owner: str, fn: str) -> None:
    assert not (ROOT / (former + ".py")).exists()
    assert (ROOT / "runtime" / (owner + ".py")).is_file()
    assert importlib.util.find_spec("picture_capture." + former) is None
    assert importlib.util.find_spec("picture_capture.runtime." + owner) is not None
    assert callable(getattr({"environment": environment, "windows_gpu": windows_gpu}[owner], fn))


def test_nvidia_wheel_loader_keeps_handles_and_path_before_engine_import(tmp_path, monkeypatch):
    wheel_site = tmp_path / "site-packages"
    cuda_bin = wheel_site / "nvidia" / "cudnn" / "bin"
    cuda_bin.mkdir(parents=True)
    (cuda_bin / "cudnn64.dll").write_bytes(b"synthetic")
    calls = []
    handles = []

    def add_dll_directory(path):
        calls.append(path)
        handle = object()
        handles.append(handle)
        return handle

    simulated_os = SimpleNamespace(name="nt", pathsep=";", environ={"PATH": "system"}, add_dll_directory=add_dll_directory)
    monkeypatch.setattr(windows_gpu, "os", simulated_os)
    monkeypatch.setattr(windows_gpu, "_site_package_roots", lambda: [wheel_site])
    monkeypatch.setattr(windows_gpu, "_DLL_DIR_HANDLES", [])
    assert windows_gpu.configure_windows_nvidia_dlls() == [cuda_bin]
    assert calls == [str(cuda_bin)]
    assert simulated_os.environ["PATH"].split(";")[0] == str(cuda_bin)
    assert windows_gpu._DLL_DIR_HANDLES == handles


def test_non_windows_loader_does_not_add_native_dll_paths(monkeypatch):
    monkeypatch.setattr(windows_gpu, "os", SimpleNamespace(name="posix"))
    assert windows_gpu.configure_windows_nvidia_dlls() == []


def test_runtime_package_has_no_eager_paddle_dependency():
    source = (ROOT / "runtime" / "__init__.py").read_text(encoding="utf-8")
    assert "import paddle" not in source
    assert "import paddleocr" not in source
