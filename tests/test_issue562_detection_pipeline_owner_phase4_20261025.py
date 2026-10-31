"""#562: real detector orchestration and ordinary worker ownership regression."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image
from picture_capture import processing
from picture_capture.detection import page_pipeline, ordinary_page_job
from picture_capture.models import AppSettings


def test_real_owners_and_public_signatures():
    assert processing.detect_entries.__module__ == "picture_capture.processing"
    assert processing.detect_entries_job.__module__ == "picture_capture.processing"
    assert "return _page_pipeline.detect_entries_impl" in inspect.getsource(processing.detect_entries)
    assert "return _ordinary_page_job.detect_entries_job_impl" in inspect.getsource(processing.detect_entries_job)
    assert "ordinary_mode = method not in" in inspect.getsource(page_pipeline.detect_entries_impl)
    assert "validate_prepared_layout" in inspect.getsource(ordinary_page_job.detect_entries_job_impl)
    assert list(inspect.signature(processing.detect_entries).parameters) == [
        "image","settings","paddle_cache_path","force_paddle_refresh",
        "paddle_filter_rules_path","profile_page_index","page_sections",
        "debug_trace","source_image_path",
    ]
    assert list(inspect.signature(processing.detect_entries_job).parameters) == [
        "image_path","settings","pages","profile_page_index","prepared_layout",
    ]


def test_detection_facade_passes_current_monkeypatched_hooks(monkeypatch):
    seen = {}
    def fake_owner(image, settings, *args, **kwargs):
        seen.update(kwargs)
        return (["test"], "geometry")
    monkeypatch.setattr(page_pipeline, "detect_entries_impl", fake_owner)
    patched = lambda *_a, **_kw: None
    monkeypatch.setattr(processing, "_understand_page_current", patched)
    image = Image.new("RGB", (16, 16), "white")
    try:
        assert processing.detect_entries(image, AppSettings()) == (["test"], "geometry")
        assert seen["deps"]["_understand_page_current"] is patched
        assert seen["deps"]["_core"] is processing._core
        assert seen["profile_page_index"] == 0
        assert seen["source_image_path"] is None
    finally:
        image.close()


def test_ordinary_fallback_keeps_shared_analysis_and_original_source(monkeypatch):
    image = Image.new("RGB", (40, 60), "white")
    settings = AppSettings()
    settings.detection_method = "left_edge"
    seen = []
    monkeypatch.setattr(processing._core, "normalize_page_rgb", lambda im: seen.append("rgb") or im)
    monkeypatch.setattr(processing._core, "effective_page_settings", lambda s, size, idx: seen.append(("profile", size, idx)) or s)
    monkeypatch.setattr(processing, "build_analysis_image", lambda im, s: seen.append("analysis") or im)
    monkeypatch.setattr(processing, "_understand_page_current", lambda *a, **kw: seen.append(("understand", kw["layout_only"])) or None)
    def fallback(analysis, source, original, effective, **kwargs):
        seen.append(("fallback", analysis is image, source is image, kwargs["profile_page_index"]))
        return ["ordinary"], "geometry"
    monkeypatch.setattr(processing, "_ordinary_vb_fallback", fallback)
    try:
        assert processing.detect_entries(image, settings, profile_page_index=7) == (["ordinary"], "geometry")
        assert seen == ["rgb", ("profile", (40, 60), 7), "analysis", ("understand", True), ("fallback", True, True, 7)]
    finally:
        image.close()


def test_ocr_unreliable_page_retains_core_detector_fallback(monkeypatch):
    image = Image.new("RGB", (30, 20), "white")
    settings = AppSettings()
    settings.detection_method = "combined"
    seen = []
    monkeypatch.setattr(processing._core, "normalize_page_rgb", lambda im: im)
    monkeypatch.setattr(processing._core, "effective_page_settings", lambda s, size, idx: s)
    monkeypatch.setattr(processing, "build_analysis_image", lambda im, s: im)
    monkeypatch.setattr(processing, "_understand_page_current", lambda *a, **kw: None)
    monkeypatch.setattr(processing, "_detect_entries_left_edge", lambda *_a, **_kw: None)
    def fallback(im, s, **kwargs):
        seen.append(kwargs)
        return ["combined"], "layout"
    monkeypatch.setattr(processing._core, "detect_entries", fallback)
    try:
        assert processing.detect_entries(image, settings, force_paddle_refresh=True) == (["combined"], "layout")
        assert seen[0]["force_paddle_refresh"] is True
        assert seen[0]["left_edge_detector"] is processing._detect_entries_left_edge
    finally:
        image.close()


def test_ordinary_job_delegates_live_io_dependencies(monkeypatch):
    seen = {}
    def fake_job(path, settings, pages, idx, *, prepared_layout, deps):
        seen["deps"] = deps
        seen["args"] = (path, settings, pages, idx, prepared_layout)
        return 5
    monkeypatch.setattr(ordinary_page_job, "detect_entries_job_impl", fake_job)
    marker = object()
    monkeypatch.setattr(processing, "replace", marker)
    settings = AppSettings()
    assert processing.detect_entries_job("page.png", settings, ("p", "a", "b"), 3) == 5
    assert seen["deps"]["replace"] is marker
    assert seen["deps"]["Image"] is processing.Image
    assert seen["args"] == ("page.png", settings, ("p", "a", "b"), 3, None)
