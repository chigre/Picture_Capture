from __future__ import annotations

import numpy as np
from PIL import Image

from picture_capture.document_unwarping import _result_output_image


class _VisualResult:
    def __init__(self, image: Image.Image):
        self.img = {"preprocessed_img": image}


def test_uvdoc_result_prefers_pil_visual_image() -> None:
    source = Image.new("RGB", (40, 30), (220, 210, 200))
    result = _result_output_image(_VisualResult(source))

    assert result.mode == "RGB"
    assert result.size == source.size
    assert result.getpixel((5, 5)) == (220, 210, 200)


def test_uvdoc_result_converts_internal_bgr_array_to_rgb() -> None:
    bgr = np.zeros((8, 12, 3), dtype=np.uint8)
    bgr[..., 0] = 10
    bgr[..., 1] = 20
    bgr[..., 2] = 230

    result = _result_output_image({"output_img": bgr})

    assert result.mode == "RGB"
    assert result.getpixel((0, 0)) == (230, 20, 10)
