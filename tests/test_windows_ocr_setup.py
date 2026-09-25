from __future__ import annotations

import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "_picture_capture_windows_ocr_setup",
    Path(__file__).resolve().parents[1] / "scripts" / "windows_ocr_setup.py",
)
assert SPEC is not None and SPEC.loader is not None
SETUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETUP)


def test_parse_cuda_version_from_nvidia_smi_banner():
    text = "| NVIDIA-SMI 581.42 Driver Version: 581.42 CUDA Version: 13.0 |"
    assert SETUP.parse_cuda_version(text) == (13, 0)


def test_gpu_recommendation_uses_highest_compatible_declared_profile():
    assert SETUP.recommended_profile({"cuda": (13, 0)})["extra"] == "ocr-gpu-cu129"
    assert SETUP.recommended_profile({"cuda": (12, 9)})["extra"] == "ocr-gpu-cu129"
    assert SETUP.recommended_profile({"cuda": (12, 8)})["extra"] == "ocr-gpu-cu126"
    assert SETUP.recommended_profile({"cuda": (12, 5)})["extra"] == "ocr-gpu-cu118"


def test_gpu_recommendation_falls_back_to_cpu_when_compatibility_is_unknown_or_too_old():
    assert SETUP.recommended_profile(None)["extra"] == "ocr-cpu"
    assert SETUP.recommended_profile({"cuda": None})["extra"] == "ocr-cpu"
    assert SETUP.recommended_profile({"cuda": (11, 7)})["extra"] == "ocr-cpu"


def test_enter_accepts_gpu_recommendation(monkeypatch):
    monkeypatch.setattr(
        SETUP,
        "detect_nvidia_gpu",
        lambda: {"gpus": [{"name": "Example GPU", "driver": "999.0"}], "cuda": (12, 9)},
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    assert SETUP.choose_profile()["extra"] == "ocr-gpu-cu129"


def test_enter_accepts_cpu_recommendation_without_supported_gpu(monkeypatch):
    monkeypatch.setattr(SETUP, "detect_nvidia_gpu", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    assert SETUP.choose_profile()["extra"] == "ocr-cpu"


def test_manual_advanced_gpu_selection_is_still_available(monkeypatch):
    answers = iter(["4", "2"])
    monkeypatch.setattr(SETUP, "detect_nvidia_gpu", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    assert SETUP.choose_profile()["extra"] == "ocr-gpu-cu126"
