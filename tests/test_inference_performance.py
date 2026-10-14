"""Unit tests for local inference policy without importing PaddleOCR."""
from __future__ import annotations

from unittest.mock import patch

from picture_capture.inference_performance import (
    InferencePolicy, paddle_constructor_variants, resolve_inference_policy,
)


def test_cpu_auto_uses_one_dnn_and_bounds_worker_threads():
    settings = {"paddle_mkldnn": "auto", "paddle_cpu_workers": "6"}
    with patch("picture_capture.inference_performance.runtime_setting",
               side_effect=lambda key, fallback: settings.get(key, fallback)), \
         patch("picture_capture.inference_performance.resolve_paddle_device", return_value="cpu"), \
         patch("picture_capture.inference_performance.os.cpu_count", return_value=24), \
         patch.dict("os.environ", {}, clear=True):
        policy = resolve_inference_policy(page_count=12)
    assert policy.cpu_workers == 6
    assert policy.cpu_threads == 4
    assert paddle_constructor_variants({}, policy) == [
        {"device": "cpu", "enable_mkldnn": True, "cpu_threads": 4},
        {"device": "cpu", "enable_mkldnn": False, "cpu_threads": 4},
    ]


def test_mkldnn_off_keeps_single_explicit_attempt():
    policy = InferencePolicy("cpu", "off", 2, 2)
    assert paddle_constructor_variants({"lang": "en"}, policy) == [
        {"lang": "en", "device": "cpu", "enable_mkldnn": False, "cpu_threads": 2},
    ]


def test_gpu_does_not_receive_cpu_specific_flags():
    policy = InferencePolicy("gpu", "auto", 6, 4)
    assert paddle_constructor_variants({}, policy) == [{"device": "gpu"}]


def test_small_batch_limits_auto_workers():
    with patch("picture_capture.inference_performance.runtime_setting",
               side_effect=lambda _key, fallback: fallback), \
         patch("picture_capture.inference_performance.resolve_paddle_device", return_value="cpu"), \
         patch("picture_capture.inference_performance.os.cpu_count", return_value=8), \
         patch.dict("os.environ", {}, clear=True):
        policy = resolve_inference_policy(page_count=2)
    assert policy.cpu_workers == 2
    assert policy.cpu_threads == 4


def test_workers_can_exceed_six():
    settings = {"paddle_mkldnn": "auto", "paddle_cpu_workers": "12"}
    with patch("picture_capture.inference_performance.runtime_setting",
               side_effect=lambda key, fallback: settings.get(key, fallback)), \
         patch("picture_capture.inference_performance.resolve_paddle_device", return_value="cpu"), \
         patch("picture_capture.inference_performance.os.cpu_count", return_value=24), \
         patch.dict("os.environ", {}, clear=True):
        policy = resolve_inference_policy(page_count=20)
    assert policy.cpu_workers == 12
    assert policy.cpu_threads == 2
