from __future__ import annotations

import pickle
from types import SimpleNamespace

from picture_capture import image_preprocessing
from picture_capture import image_preprocessing_canvas as canvas_helpers


def test_phase7o_stable_module_reexports_canvas_helpers() -> None:
    assert (
        image_preprocessing._normalize_canvas_alignment
        is canvas_helpers._normalize_canvas_alignment
    )
    assert image_preprocessing.output_canvas_info is canvas_helpers.output_canvas_info


def test_phase7o_output_canvas_info_keeps_historical_callable_path() -> None:
    helper = image_preprocessing.output_canvas_info

    assert helper.__module__ == "picture_capture.image_preprocessing"
    assert pickle.loads(pickle.dumps(helper)) is helper


def test_output_canvas_info_keeps_margin_alignment_contract() -> None:
    analysis = SimpleNamespace(crop_box=(10, 20, 110, 220))

    canvas = image_preprocessing.output_canvas_info(
        analysis,
        enabled=True,
        mode="custom",
        requested_width=150,
        requested_height=260,
        margin_top=15,
        margin_bottom=25,
        margin_left=10,
        margin_right=20,
        align_x="right",
        align_y="bottom",
    )

    assert (canvas.width, canvas.height) == (150, 260)
    assert canvas.body_box == (10, 15, 130, 235)
    assert canvas.content_box == (30, 35, 130, 235)
    assert canvas.align_x == "right"
    assert canvas.align_y == "bottom"


def test_output_canvas_info_normalizes_invalid_alignment() -> None:
    analysis = SimpleNamespace(crop_box=(0, 0, 100, 200))

    canvas = image_preprocessing.output_canvas_info(
        analysis,
        enabled=True,
        canvas_width=130,
        canvas_height=230,
        align_x="unexpected",
        align_y="unexpected",
    )

    assert canvas.align_x == "center"
    assert canvas.align_y == "top"
    assert canvas.content_box == (15, 0, 115, 200)
