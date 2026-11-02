"""R7.3 RED-first: detect multiple stage-coordinate extrema in one interval."""
from __future__ import annotations

import pytest

from picture_capture.preprocess.coordinate_mapping import PreprocessCoordinateMap
from picture_capture.preprocess.models import PreprocessAnalysis


def _mapping() -> PreprocessCoordinateMap:
    step = {
        "row_gain": 1.0,
        "reference_x": 0.0,
        "y_knots": [],
        "angle_knots_deg": [],
        "x_knots": [],
        "row_grid_rows": 0,
        "row_grid_cols": 0,
        "row_angle_grid_deg": [],
        "row_displacement_grid_px": [],
        "separator_y_knots": [0.0, 99.0],
        "separator_shift_knots_px": [0.0, 0.0],
    }
    analysis = PreprocessAnalysis(
        source_width=100,
        source_height=100,
        correction_angle_deg=0.0,
        applied_angle_deg=0.0,
        crop_box=(0, 0, 100, 100),
        raw_content_box=(0, 0, 100, 100),
        text_box=(0, 0, 100, 100),
        source_boxes=0,
        angle_samples=0,
        angle_mad_deg=0.0,
        retained_ratio=1.0,
        confidence=1.0,
        status="synthetic",
        method="r7_3_multiple_extrema_between_knots",
        geometry_mode="perspective",
        perspective_matrix=None,
        orthogonal_applied=True,
        orthogonal_steps=(step,),
    )
    return PreprocessCoordinateMap(analysis)


def _quartic_stage_y(t: float) -> float:
    # Its derivative is (t - 0.32) * (t - 0.37) * (t + 1).
    # This gives two close extrema inside one coarse sample interval, while
    # the old five derivative probes all observe a positive derivative.
    a, b = 0.32, 0.37
    return (
        t**4 / 4.0
        + (1.0 - a - b) * t**3 / 3.0
        + (a * b - a - b) * t**2 / 2.0
        + a * b * t
    )


def _quartic_derivative(t: float) -> float:
    return (t - 0.32) * (t - 0.37) * (t + 1.0)


@pytest.mark.parametrize("reverse", (False, True))
def test_stage_extrema_finds_two_close_turns_between_coarse_derivative_probes(
    monkeypatch, reverse,
):
    mapping = _mapping()

    # Model the stage-input coordinate along one already-partitioned edge
    # interval. A composition of nonlinear mesh stages can produce a
    # higher-order path even when each individual stage is locally smooth.
    def stage_input(self, point, stage_index, *, reverse):
        t = float(point[0])
        return (t, _quartic_stage_y(t))

    monkeypatch.setattr(
        PreprocessCoordinateMap,
        "_orthogonal_stage_input_point",
        stage_input,
    )

    assert all(
        _quartic_derivative(t) > 0.0
        for t in (0.001, 0.25, 0.5, 0.75, 0.999)
    )
    assert _quartic_derivative(0.34375) < 0.0

    extrema = mapping._orthogonal_stage_extrema(
        (0.0, 0.0),
        (1.0, 0.0),
        0.0,
        1.0,
        0,
        1,
        reverse=reverse,
    )
    assert extrema == pytest.approx((0.32, 0.37), abs=1e-6)
