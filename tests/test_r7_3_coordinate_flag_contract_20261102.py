"""R7.3 RED-first strict boolean contracts for coordinate-map flags."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from picture_capture.geometry.layout_transform import LayoutTransform
from picture_capture.preprocess.coordinate_mapping import PreprocessCoordinateMap
from picture_capture.preprocess.models import OutputCanvasInfo, PreprocessAnalysis


def _analysis(width=80, height=100) -> PreprocessAnalysis:
    return PreprocessAnalysis(
        source_width=width,
        source_height=height,
        correction_angle_deg=0.0,
        applied_angle_deg=0.0,
        crop_box=(0, 0, width, height),
        raw_content_box=(0, 0, width, height),
        text_box=(0, 0, width, height),
        source_boxes=0,
        angle_samples=0,
        angle_mad_deg=0.0,
        retained_ratio=1.0,
        confidence=1.0,
        status="synthetic",
        method="r7_3_coordinate_flag_contract",
        geometry_mode="perspective",
        perspective_matrix=None,
        orthogonal_applied=False,
        orthogonal_steps=(),
    )


def _canvas(enabled=True) -> OutputCanvasInfo:
    return OutputCanvasInfo(
        enabled=enabled,
        mode="custom",
        requested_width=80,
        requested_height=100,
        width=80,
        height=100,
        margin_top=0,
        margin_bottom=0,
        margin_left=0,
        margin_right=0,
        body_box=(0, 0, 80, 100),
        align_x="center",
        align_y="center",
        content_box=(0, 0, 80, 100),
    )


@pytest.mark.parametrize("flag", ("false", 1, 0))
def test_analysis_is_canonicalized_requires_a_boolean(flag):
    transform = LayoutTransform("rotate_ccw90")
    with pytest.raises(ValueError, match="analysis_is_canonicalized"):
        PreprocessCoordinateMap(
            _analysis(),
            source_size=(100, 80),
            layout_transform=transform,
            analysis_is_canonicalized=flag,
        )


def test_analysis_is_canonicalized_accepts_numpy_boolean_scalar():
    transform = LayoutTransform("rotate_ccw90")
    mapping = PreprocessCoordinateMap(
        _analysis(),
        source_size=(100, 80),
        layout_transform=transform,
        analysis_is_canonicalized=np.bool_(True),
    )
    assert mapping.analysis_is_canonicalized is True


@pytest.mark.parametrize("enabled", ("false", 1, 0))
def test_output_canvas_enabled_requires_a_boolean(enabled):
    with pytest.raises(ValueError, match="canvas enabled"):
        PreprocessCoordinateMap(
            _analysis(),
            canvas=_canvas(enabled=enabled),
        )


def test_output_canvas_enabled_accepts_and_snapshots_numpy_boolean_scalar():
    mapping = PreprocessCoordinateMap(
        _analysis(),
        canvas=_canvas(enabled=np.bool_(True)),
    )
    assert mapping.canvas is not None
    assert mapping.canvas.enabled is True
    assert type(mapping.canvas.enabled) is bool
