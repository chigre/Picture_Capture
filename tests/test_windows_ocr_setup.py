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


def test_parse_cuda_version_from_nvidia_smi_banner():
    text = "| NVIDIA-SMI 581.42 Driver Version: 581.42 CUDA Version: 13.0 |"
    assert SETUP.parse_cuda_version(text) == (13, 0)


def test_parse_compute_capability():
    assert SETUP.parse_compute_capability("8.9") == (8, 9)
    assert SETUP.parse_compute_capability(" 10.0 ") == (10, 0)
    assert SETUP.parse_compute_capability("N/A") is None


def test_parse_gpu_query_rows_with_compute_capability():
    rows = SETUP.parse_gpu_query_rows(
        '0, "NVIDIA GeForce RTX 4070", 581.42, 8.9\n'
        '1, "NVIDIA RTX A6000", 581.42, 8.6\n',
        with_compute_cap=True,
    )
    assert rows == [
        {"index": "0", "name": "NVIDIA GeForce RTX 4070", "driver": "581.42", "compute_cap": (8, 9)},
        {"index": "1", "name": "NVIDIA RTX A6000", "driver": "581.42", "compute_cap": (8, 6)},
    ]


def test_gpu_recommendation_uses_highest_compatible_declared_profile():
    assert SETUP.recommended_profile(gpu_info(cuda=(13, 0)))["extra"] == "ocr-gpu-cu129"
    assert SETUP.recommended_profile(gpu_info(cuda=(12, 9)))["extra"] == "ocr-gpu-cu129"
    assert SETUP.recommended_profile(gpu_info(cuda=(12, 8)))["extra"] == "ocr-gpu-cu126"
    assert SETUP.recommended_profile(gpu_info(cuda=(12, 5)))["extra"] == "ocr-gpu-cu118"


def test_gpu_recommendation_requires_documented_compute_capability_over_7_5():
    assert SETUP.recommended_profile(gpu_info(compute_cap=(8, 0)))["extra"] == "ocr-gpu-cu129"
    assert SETUP.recommended_profile(gpu_info(compute_cap=(7, 5)))["extra"] == "ocr-cpu"
    assert SETUP.recommended_profile(gpu_info(compute_cap=(7, 0)))["extra"] == "ocr-cpu"
    assert SETUP.recommended_profile(gpu_info(compute_cap=None))["extra"] == "ocr-cpu"


def test_gpu_recommendation_falls_back_to_cpu_when_cuda_is_unknown_or_too_old():
    assert SETUP.recommended_profile(None)["extra"] == "ocr-cpu"
    assert SETUP.recommended_profile(gpu_info(cuda=None))["extra"] == "ocr-cpu"
    assert SETUP.recommended_profile(gpu_info(cuda=(11, 7)))["extra"] == "ocr-cpu"


def test_primary_gpu_uses_index_zero_for_runtime_recommendation():
    info = {
        "gpus": [
            {"index": "1", "name": "New GPU", "driver": "1", "compute_cap": (9, 0)},
            {"index": "0", "name": "Primary GPU", "driver": "1", "compute_cap": (7, 5)},
        ],
        "cuda": (12, 9),
    }
    assert SETUP.primary_gpu(info)["name"] == "Primary GPU"
    assert SETUP.recommended_profile(info)["extra"] == "ocr-cpu"


def test_enter_accepts_gpu_recommendation(monkeypatch):
    monkeypatch.setattr(SETUP, "detect_nvidia_gpu", lambda: gpu_info())
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    assert SETUP.choose_profile()["extra"] == "ocr-gpu-cu129"


def test_enter_accepts_cpu_recommendation_without_supported_gpu(monkeypatch):
    monkeypatch.setattr(SETUP, "detect_nvidia_gpu", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    assert SETUP.choose_profile()["extra"] == "ocr-cpu"


def test_enter_accepts_cpu_recommendation_when_compute_capability_is_insufficient(monkeypatch):
    monkeypatch.setattr(SETUP, "detect_nvidia_gpu", lambda: gpu_info(compute_cap=(7, 5)))
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    assert SETUP.choose_profile()["extra"] == "ocr-cpu"


def test_manual_advanced_gpu_selection_is_still_available(monkeypatch):
    answers = iter(["4", "2"])
    monkeypatch.setattr(SETUP, "detect_nvidia_gpu", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    assert SETUP.choose_profile()["extra"] == "ocr-gpu-cu126"
