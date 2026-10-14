"""Opt-in CPU-only ordinary pool guards; never starts six GPU copies.

These tests use synthetic inputs and injected detector classes. They cannot
measure real CPU throughput or prove GPU/CPU text polygon parity.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from picture_capture.ordinary_cpu_pool import (
    cpu_pool_enabled, cpu_pool_config, cpu_ordinary_page_job,
)


def test_cpu_pool_is_explicit_only_and_rejects_unproven_mask_or_rotation():
    settings = SimpleNamespace(
        ordinary_auto_layout=True, layout_mask_illustrations=False,
        layout_transform="identity",
    )
    assert cpu_pool_enabled(settings, 18, flag="1")
    assert not cpu_pool_enabled(settings, 1, flag="1")
    assert not cpu_pool_enabled(settings, 18, flag="")
    settings.layout_mask_illustrations = True
    assert not cpu_pool_enabled(settings, 18, flag="1")
    settings.layout_mask_illustrations = False
    settings.layout_transform = "rotate_ccw90"
    assert not cpu_pool_enabled(settings, 18, flag="1")


def test_24_cpu_workers_and_threads_bounded_independently():
    assert cpu_pool_config(30, cpus=24, requested_workers="") == (2, 4)
    assert cpu_pool_config(30, cpus=24, requested_workers="4") == (4, 4)
    assert cpu_pool_config(30, cpus=24, requested_workers="6") == (6, 4)
    assert cpu_pool_config(30, cpus=24, requested_workers="12") == (12, 2)
    assert cpu_pool_config(30, cpus=24, requested_workers="6",
                           requested_threads="3") == (6, 3)
    assert cpu_pool_config(30, cpus=8, requested_workers="6") == (6, 1)
    assert cpu_pool_config(30, cpus=24, requested_workers="100") == (24, 1)
    assert cpu_pool_config(30, cpus=24, requested_workers="3") == (3, 4)
    assert cpu_pool_config(1, cpus=24, requested_workers="6") == (1, 4)
    assert cpu_pool_config(100, cpus=4, requested_workers="6",
                           requested_threads="99") == (4, 1)


def test_cpu_worker_forces_device_and_reuses_original_pdics_writer(monkeypatch):
    # processing is a mirrored facade: patching its public function also
    # mutates processing_core via facade_compat. Restore BOTH namespaces
    # before any subsequent tests to avoid a false legacy-ownership failure.
    from picture_capture import processing, processing_core
    from picture_capture.runtime_environment import resolve_paddle_device

    original_core = processing_core.detect_entries_job
    observed = []
    with monkeypatch.context() as isolated:
        isolated.setenv("PICTURE_CAPTURE_PADDLE_DEVICE", "gpu")
        isolated.setattr(
            processing, "detect_entries_job",
            lambda *args: observed.append(args) or 17,
        )
        try:
            assert cpu_ordinary_page_job(
                "synthetic.png", "s", ("p", "@", "@"), 9, 3
            ) == 17
            assert os.environ["PICTURE_CAPTURE_PADDLE_DEVICE"] == "cpu"
            assert os.environ["PICTURE_CAPTURE_ORDINARY_CPU_POOL_WORKER"] == "1"
            assert os.environ["OMP_NUM_THREADS"] == "3"
            assert resolve_paddle_device() == "cpu"
            assert observed == [("synthetic.png", "s", ("p", "@", "@"), 9)]
        finally:
            resolve_paddle_device.cache_clear()
    processing_core.detect_entries_job = original_core


def test_cpu_only_detector_explicit_threads_no_gpu_fallback(monkeypatch):
    from picture_capture import layout_detection_legacy as legacy
    from picture_capture.runtime_environment import resolve_paddle_device

    observed = []
    fake = ModuleType("paddleocr")

    class TextDetection:
        def __init__(self, **kwargs):
            observed.append(dict(kwargs))
        def predict(self, *a, **kw):
            return []

    fake.TextDetection = TextDetection
    monkeypatch.setitem(sys.modules, "paddleocr", fake)
    monkeypatch.setenv("PICTURE_CAPTURE_ORDINARY_CPU_POOL_WORKER", "1")
    monkeypatch.setenv("OMP_NUM_THREADS", "3")
    monkeypatch.setenv("PICTURE_CAPTURE_PADDLE_DEVICE", "gpu")
    monkeypatch.setenv("PICTURE_CAPTURE_PADDLE_MKLDNN", "off")
    legacy._TEXT_DETECTION_CACHE.clear()
    try:
        one = legacy._get_text_detector(SimpleNamespace())
        two = legacy._get_text_detector(SimpleNamespace())
        assert one is two
        assert observed == [{
            "enable_mkldnn": False, "device": "cpu", "cpu_threads": 3,
        }]
    finally:
        legacy._TEXT_DETECTION_CACHE.clear()
        resolve_paddle_device.cache_clear()


def test_cpu_only_constructor_incompatibility_must_abort_not_attempt_gpu(monkeypatch):
    from picture_capture import layout_detection_legacy as legacy

    received = []
    fake = ModuleType("paddleocr")

    class TextDetection:
        def __init__(self, **kwargs):
            received.append(kwargs)
            raise TypeError("cpu_threads unavailable")

    fake.TextDetection = TextDetection
    monkeypatch.setitem(sys.modules, "paddleocr", fake)
    monkeypatch.setenv("PICTURE_CAPTURE_ORDINARY_CPU_POOL_WORKER", "1")
    monkeypatch.setenv("OMP_NUM_THREADS", "4")
    legacy._TEXT_DETECTION_CACHE.clear()
    with pytest.raises(RuntimeError, match="初始化失败"):
        legacy._get_text_detector(SimpleNamespace())
    assert len(received) == 1
    assert received[0]["device"] == "cpu"
    assert received[0]["cpu_threads"] == 4
    legacy._TEXT_DETECTION_CACHE.clear()


def test_cpu_only_pool_gui_dispatch_keeps_gpu_experiment_mutually_exclusive():
    src = (
        Path(__file__).resolve().parents[1] / "src"
        / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    a = src.index("    def _detect_pages(")
    b = src.index("\n    def clear_entries(", a)
    part = src[a:b]
    assert "and not cpu_pool" in part
    assert "elif cpu_pool and cpu_pool_workers > 1:" in part
    assert "cpu_ordinary_page_job," in part
    assert "max_workers=cpu_pool_workers" in part
    assert "foreground_page_edit=True" in part
    assert "if normal_executor is not None:" in part
    assert "cpu_ordinary_page_job, str(page), settings," in part
    assert "ordinary_workers = cpu_pool_workers" in part
