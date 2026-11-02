"""R7.3 RED-first synthetic canvas raster snapshot contract tests.

No real image pages or private PDIC/PPP/SECTION/Profile/OCR records are used.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from picture_capture.preprocess.coordinate_mapping import PreprocessCoordinateMap
from picture_capture.preprocess.models import OutputCanvasInfo, PreprocessAnalysis


def _analysis() -> PreprocessAnalysis:
    return PreprocessAnalysis(
        source_width=100,
        source_height=100,
        correction_angle_deg=0.0,
        applied_angle_deg=0.0,
        crop_box=(10, 20, 60, 80),
        raw_content_box=(10, 20, 60, 80),
        text_box=(10, 20, 60, 80),
        source_boxes=0,
        angle_samples=0,
        angle_mad_deg=0.0,
        retained_ratio=1.0,
        confidence=1.0,
        status="synthetic",
        method="r7_3_canvas_raster_snapshot",
    )


def _canvas() -> OutputCanvasInfo:
    return OutputCanvasInfo(
        enabled=True,
        mode="custom",
        requested_width=100,
        requested_height=100,
        width=100,
        height=100,
        margin_top=10,
        margin_bottom=10,
        margin_left=10,
        margin_right=10,
        body_box=(10, 10, 90, 90),
        align_x="center",
        align_y="center",
        content_box=(10, 10, 60, 70),
    )


def test_valid_integer_canvas_preserves_forward_and_inverse_crop_offsets():
    mapping = PreprocessCoordinateMap(_analysis(), canvas=_canvas())
    forward = mapping.source_to_output_point((15.0, 25.0))
    assert forward.status == "mapped"
    assert forward.point == (15.0, 15.0)
    inverse = mapping.output_to_source_point(forward.point)
    assert inverse.status == "mapped"
    assert inverse.point == pytest.approx((15.0, 25.0))


def test_numpy_integer_canvas_is_snapshotted_to_plain_integer_raster_values():
    canvas = replace(
        _canvas(),
        width=np.int64(100),
        height=np.int64(100),
        content_box=np.asarray((10, 10, 60, 70), dtype=np.int64),
    )
    mapping = PreprocessCoordinateMap(_analysis(), canvas=canvas)
    assert mapping.canvas is not None
    assert mapping.canvas.width == 100
    assert mapping.canvas.height == 100
    assert mapping.canvas.content_box == (10, 10, 60, 70)
    assert type(mapping.canvas.width) is int
    assert type(mapping.canvas.content_box[0]) is int


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("width", 100.5),
        ("width", True),
        ("width", "100"),
        ("width", 0),
        ("height", 100.25),
        ("height", True),
        ("height", float("inf")),
        ("height", -1),
    ),
)
def test_canvas_rejects_noninteger_or_nonpositive_raster_dimensions(field, value):
    with pytest.raises(ValueError, match="canvas dimensions"):
        PreprocessCoordinateMap(
            _analysis(),
            canvas=replace(_canvas(), **{field: value}),
        )


@pytest.mark.parametrize(
    "box",
    (
        (10.5, 10, 60.5, 70),
        (True, 10, 51, 70),
        (10, 10.5, 60, 70.5),
        (10, 10, 60, True),
        (10, 10, 60),
        (10, 10, 60, 70, 80),
        "10,10,60,70",
    ),
)
def test_canvas_rejects_fractional_boolean_or_malformed_content_box(box):
    with pytest.raises(ValueError, match="canvas content_box"):
        PreprocessCoordinateMap(
            _analysis(),
            canvas=replace(_canvas(), content_box=box),
        )


def test_canvas_retains_a_stable_content_offset_when_caller_mutates_a_list():
    caller_box = [10, 10, 60, 70]
    supplied = replace(_canvas(), content_box=caller_box)
    mapping = PreprocessCoordinateMap(_analysis(), canvas=supplied)
    before = mapping.source_to_output_point((15.0, 25.0))
    assert before.point == (15.0, 15.0)

    caller_box[0] = 20
    caller_box[2] = 70
    after = mapping.source_to_output_point((15.0, 25.0))
    assert after == before
    assert mapping.canvas is not None
    assert mapping.canvas.content_box == (10, 10, 60, 70)


def test_actual_canvas_factory_produces_an_accepted_raster_snapshot():
    from picture_capture.preprocess.canvas import output_canvas_info

    analysis = _analysis()
    canvas = output_canvas_info(
        analysis,
        enabled=True,
        mode="custom",
        canvas_width=100,
        canvas_height=100,
        requested_width=100,
        requested_height=100,
        margin_top=10,
        margin_bottom=10,
        margin_left=10,
        margin_right=10,
    )
    mapping = PreprocessCoordinateMap(analysis, canvas=canvas)
    mapped = mapping.source_to_output_point((15.0, 25.0))
    assert mapped.status == "mapped"
    assert mapped.point is not None
    assert mapped.point[0] == pytest.approx(canvas.content_box[0] + 5)
    assert mapped.point[1] == pytest.approx(canvas.content_box[1] + 5)
