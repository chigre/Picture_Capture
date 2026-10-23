"""Issue #562: explicit UVDoc and post-perspective redetection stage contracts."""
from __future__ import annotations

import subprocess
import sys

import numpy as np
from PIL import Image
import pytest

from picture_capture.preprocess import geometry_stages as stages


@pytest.fixture
def inputs():
    image = Image.new("RGB", (40, 60), (10, 20, 30))
    polygons = [np.zeros((4, 2), dtype=float)]
    settings = object()
    return image, polygons, settings


def test_leaf_import_does_not_load_facade_gui_or_paddle():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.preprocess.geometry_stages import PostPerspectiveRedetection
assert 'picture_capture.preprocess.pipeline' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


@pytest.mark.parametrize("requested", ["auto", "deskew", "perspective"])
def test_non_uvdoc_modes_keep_original_objects_and_never_call_unwarper(inputs, requested):
    image, polygons, _ = inputs
    warnings, methods, calls = ["prior"], ["deskew"], []
    def unwarp(candidate):
        calls.append(candidate)
        raise AssertionError("must not run")
    result = stages.apply_explicit_uvdoc(
        image, polygons, "deskew", requested_geometry_mode=requested,
        document_unwarper=unwarp, warnings=warnings, method_parts=methods)
    assert result.image is image and result.polygons is polygons
    assert result.geometry_mode == "deskew" and not calls
    assert warnings == ["prior"] and methods == ["deskew"]


def test_uvdoc_success_uses_current_unwarper_clears_polygons_and_appends_method(inputs):
    image, polygons, _ = inputs
    after = Image.new("RGB", image.size, (50, 60, 70))
    calls, warnings, methods = [], [], ["deskew"]
    def unwarp(value):
        calls.append(value)
        return after
    result = stages.apply_explicit_uvdoc(
        image, polygons, "manual_perspective", requested_geometry_mode="uvdoc",
        document_unwarper=unwarp, warnings=warnings, method_parts=methods)
    assert calls == [image] and result.image is after
    assert result.polygons == [] and result.polygons is not polygons
    assert result.geometry_mode == "uvdoc"
    assert methods == ["deskew", "uvdoc"] and warnings == []
    assert len(polygons) == 1


def test_uvdoc_failure_keeps_prior_geometry_and_exact_warning_order(inputs):
    image, polygons, _ = inputs
    warnings, methods = ["earlier"], ["manual_perspective"]
    def failure(value):
        assert value is image
        raise RuntimeError("not installed")
    result = stages.apply_explicit_uvdoc(
        image, polygons, "manual_perspective", requested_geometry_mode="uvdoc",
        document_unwarper=failure, warnings=warnings, method_parts=methods)
    assert result.image is image and result.polygons is polygons
    assert result.geometry_mode == "manual_perspective"
    assert warnings == ["earlier",
        "Paddle UVDoc 展平不可用，已保留前一步几何结果：not installed"]
    assert methods == ["manual_perspective"]


@pytest.mark.parametrize("requested,actual,nonempty", [
    ("deskew", "perspective", True),
    ("perspective", "perspective", True),
    ("uvdoc", "perspective", True),
    ("auto", "deskew", True),
    ("auto", "manual_perspective", True),
    ("auto", "perspective", False),
])
def test_redetection_requires_auto_warp_and_original_boxes(inputs, requested, actual, nonempty):
    image, polygons, settings = inputs
    old = polygons if nonempty else []
    warnings, methods = [], []
    def forbidden(*args):
        raise AssertionError("unrequested redetection")
    result = stages.redetect_after_perspective(
        image, old, settings, requested_geometry_mode=requested,
        actual_geometry_mode=actual, text_detector=forbidden,
        min_boxes=8, warnings=warnings, method_parts=methods)
    assert result.polygons is old and not result.redetected
    assert warnings == [] and methods == []


@pytest.mark.parametrize("count", [0, 7, 8, 9])
def test_post_perspective_detection_minimum_is_inclusive(inputs, count):
    image, polygons, settings = inputs
    warnings, methods, calls = ["prior"], ["perspective"], []
    def detector(*args):
        calls.append(args)
        return [[(1, 2), (3, 4), (5, 6), (7, 8)] for _ in range(count)]
    result = stages.redetect_after_perspective(
        image, polygons, settings, requested_geometry_mode="auto",
        actual_geometry_mode="perspective", text_detector=detector,
        min_boxes=8, warnings=warnings, method_parts=methods)
    assert calls == [(image, settings)]
    assert result.redetected is (count >= 8)
    if count >= 8:
        assert len(result.polygons) == count and result.polygons is not polygons
        assert result.polygons[0].dtype == float and result.polygons[0].shape == (4, 2)
        assert methods == ["perspective", "post_perspective_redetect"]
        assert warnings == ["prior"]
    else:
        assert result.polygons is polygons and methods == ["perspective"]
        assert warnings == ["prior",
            "透视后正文复检文本框不足，正交细化沿用变换后的原检测框。"]


@pytest.mark.parametrize("failure", ["detector", "conversion"])
def test_redetection_failure_preserves_boxes_with_original_warning(inputs, failure):
    image, polygons, settings = inputs
    warnings, methods = ["first"], ["perspective"]
    def detector(*args):
        if failure == "detector":
            raise RuntimeError("OCR fail")
        return [object()] * 8
    result = stages.redetect_after_perspective(
        image, polygons, settings, requested_geometry_mode="auto",
        actual_geometry_mode="perspective", text_detector=detector,
        min_boxes=8, warnings=warnings, method_parts=methods)
    assert result.polygons is polygons and not result.redetected
    assert len(warnings) == 2 and warnings[0] == "first"
    assert warnings[1].startswith("透视后正文复检不可用，正交细化沿用变换后的原检测框：")
    assert methods == ["perspective"]


def test_success_returns_new_float_arrays_without_modifying_inputs(inputs):
    image, polygons, settings = inputs
    source = [np.arange(8, dtype=np.int32).reshape(4, 2)] * 8
    result = stages.redetect_after_perspective(
        image, polygons, settings, requested_geometry_mode="auto",
        actual_geometry_mode="perspective", text_detector=lambda *_: source,
        min_boxes=8, warnings=[], method_parts=[])
    assert result.redetected
    assert result.polygons[0].dtype == np.float64
    assert np.array_equal(result.polygons[0], source[0])
    assert result.polygons[0] is not source[0]
    assert polygons[0].shape == (4, 2)
