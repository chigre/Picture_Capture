from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess


SPEC = importlib.util.spec_from_file_location(
    "_picture_capture_ocr_setup",
    Path(__file__).resolve().parents[1] / "scripts" / "ocr_setup.py",
)
assert SPEC is not None and SPEC.loader is not None
SETUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETUP)


def support(system: str, machine: str):
    return SETUP.platform_support(system, machine)


def gpu_info(cuda=(12, 9), compute_cap=(8, 6)):
    return {
        "gpus": [{
            "index": "0",
            "name": "Example GPU",
            "driver": "999.0",
            "compute_cap": compute_cap,
        }],
        "cuda": cuda,
    }


def test_platform_support_matrix():
    windows = support("Windows", "AMD64")
    assert windows["paddle_cpu"] is True
    assert windows["paddle_gpu"] is True

    linux_x64 = support("Linux", "x86_64")
    assert linux_x64["paddle_cpu"] is True
    assert linux_x64["paddle_gpu"] is True

    linux_arm = support("Linux", "aarch64")
    assert linux_arm["paddle_cpu"] is True
    assert linux_arm["paddle_gpu"] is False

    mac_arm = support("Darwin", "arm64")
    assert mac_arm["paddle_cpu"] is True
    assert mac_arm["paddle_gpu"] is False

    mac_intel = support("Darwin", "x86_64")
    assert mac_intel["paddle_cpu"] is False
    assert mac_intel["paddle_gpu"] is False


def test_recommendation_respects_platform_before_gpu_detection():
    assert SETUP.recommended_profile(gpu_info(), support("Darwin", "arm64"))["extra"] == "ocr-cpu"
    assert SETUP.recommended_profile(gpu_info(), support("Linux", "aarch64"))["extra"] == "ocr-cpu"
    assert SETUP.recommended_profile(gpu_info(), support("Darwin", "x86_64"))["extra"] is None


def test_nvidia_platforms_select_highest_compatible_gpu_profile():
    win = support("Windows", "AMD64")
    linux = support("Linux", "x86_64")
    assert SETUP.recommended_profile(gpu_info(cuda=(13, 0)), win)["extra"] == "ocr-gpu-cu129"
    assert SETUP.recommended_profile(gpu_info(cuda=(12, 8)), linux)["extra"] == "ocr-gpu-cu126"
    assert SETUP.recommended_profile(gpu_info(cuda=(12, 5)), linux)["extra"] == "ocr-gpu-cu118"


def test_nvidia_recommendation_still_requires_compute_capability_over_7_5():
    win = support("Windows", "AMD64")
    assert SETUP.recommended_profile(gpu_info(compute_cap=(7, 5)), win)["extra"] == "ocr-cpu"
    assert SETUP.recommended_profile(gpu_info(compute_cap=None), win)["extra"] == "ocr-cpu"


def test_profile_supported_blocks_paddle_where_official_wheel_is_not_supported():
    mac_intel = support("Darwin", "x86_64")
    mac_arm = support("Darwin", "arm64")
    assert SETUP.profile_supported(SETUP.CPU_PROFILE, mac_intel) is False
    assert SETUP.profile_supported(SETUP.GPU_PROFILES[0], mac_intel) is False
    assert SETUP.profile_supported(SETUP.CPU_PROFILE, mac_arm) is True
    assert SETUP.profile_supported(SETUP.GPU_PROFILES[0], mac_arm) is False
    assert SETUP.profile_supported(SETUP.LENS_PROFILE, mac_intel) is True
    assert SETUP.profile_supported(SETUP.CORE_PROFILE, mac_intel) is True


def test_mac_arm_enter_accepts_cpu_recommendation(monkeypatch):
    monkeypatch.setattr(SETUP, "platform_support", lambda: support("Darwin", "arm64"))
    monkeypatch.setattr(SETUP, "detect_nvidia_gpu", lambda: (_ for _ in ()).throw(AssertionError("GPU detection should not run")))
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    assert SETUP.choose_profile()["extra"] == "ocr-cpu"


def test_intel_mac_enter_accepts_core_recommendation(monkeypatch):
    monkeypatch.setattr(SETUP, "platform_support", lambda: support("Darwin", "x86_64"))
    monkeypatch.setattr(SETUP, "detect_nvidia_gpu", lambda: (_ for _ in ()).throw(AssertionError("GPU detection should not run")))
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    assert SETUP.choose_profile()["extra"] is None


def test_linux_x64_enter_accepts_gpu_recommendation(monkeypatch):
    monkeypatch.setattr(SETUP, "platform_support", lambda: support("Linux", "x86_64"))
    monkeypatch.setattr(SETUP, "detect_nvidia_gpu", lambda: gpu_info())
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    assert SETUP.choose_profile()["extra"] == "ocr-gpu-cu129"


def test_legacy_windows_wrapper_exports_cross_platform_api():
    wrapper_spec = importlib.util.spec_from_file_location(
        "_picture_capture_windows_ocr_setup",
        Path(__file__).resolve().parents[1] / "scripts" / "windows_ocr_setup.py",
    )
    assert wrapper_spec is not None and wrapper_spec.loader is not None
    wrapper = importlib.util.module_from_spec(wrapper_spec)
    wrapper_spec.loader.exec_module(wrapper)
    assert wrapper.PROFILES["2"]["extra"] == "ocr-gpu-cu118"
    assert wrapper.platform_support("Linux", "x86_64")["paddle_gpu"] is True


def test_cross_platform_ci_and_release_packaging():
    root = Path(__file__).resolve().parents[1]
    ci = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for runner in ("ubuntu-latest", "windows-latest", "macos-latest"):
        assert runner in ci
    assert "scripts/ci_platform_check.py" in ci

    release = (root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "src scripts docs examples" in release
    for name in (
        "run_windows.bat", "install_ocr_windows.bat",
        "run_linux.sh", "install_ocr_linux.sh",
        "run_macos.command", "install_ocr_macos.command",
    ):
        assert name in release


def test_posix_launcher_shell_syntax_when_shell_is_available():
    shell = shutil.which("sh")
    if shell is None:
        return
    root = Path(__file__).resolve().parents[1]
    for name in (
        "run_linux.sh", "install_ocr_linux.sh",
        "run_macos.command", "install_ocr_macos.command",
    ):
        subprocess.run([shell, "-n", str(root / name)], check=True)
