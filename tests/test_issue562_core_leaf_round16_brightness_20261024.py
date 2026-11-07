"""Regression characterization for round 16 legacy VB brightness leaves."""

import numpy as np

from picture_capture import processing_core as core
from picture_capture.ordinary import legacy_brightness_sampling as leaf


def test_legacy_point_retains_inclusive_row_gate():
    # Inclusive 3 rows but historical denominator is area_x * area_y.
    pixels = np.zeros((7, 8), dtype=np.int64)
    pixels[2:5, 3:5] = 765
    assert core._legacy_is_point(pixels, 2, 3, 2, 2, 150) is True
    assert core._legacy_is_point(pixels, 2, 3, 2, 2, 50) is False
    assert core._legacy_is_point(pixels, 0, 0, 2, 2, 150) is False
    assert core._legacy_is_point.__module__ == "picture_capture.processing_core"


def test_legacy_row_scale_bounds_and_direction():
    pixels = np.zeros((4, 8), dtype=np.int64)
    pixels[1, 3:5] = 765
    assert core._legacy_row_brightness_1000(pixels, 1, 2, 2) == 1000
    assert core._legacy_row_brightness_1000(pixels, 1, 5, 2, direction=-1) == 1000
    assert core._legacy_row_brightness_1000(pixels, 1, 0, 2, direction=-1) is None
    assert core._legacy_row_brightness_1000(pixels, 9, 2, 2) is None
    assert core._legacy_row_brightness_1000.__module__ == "picture_capture.processing_core"


def test_numpy_dependency_is_live(monkeypatch):
    class ArrayProxy:
        int64 = np.int64
        float64 = np.float64
        @staticmethod
        def arange(*args, **kwargs):
            ArrayProxy.called = True
            return np.arange(*args, **kwargs)
    ArrayProxy.called = False
    monkeypatch.setattr(core, "np", ArrayProxy)
    pixels = np.zeros((5, 5), dtype=np.int64)
    assert core._legacy_row_brightness_1000(pixels, 2, 1, 2) == 0
    assert ArrayProxy.called
    assert leaf.legacy_row_brightness_1000(pixels, 2, 1, 2, np_module=np) == 0
