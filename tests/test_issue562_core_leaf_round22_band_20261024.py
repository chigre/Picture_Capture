"""Round 22: column OCR band pixel parity and OCR scalar helper owners."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from picture_capture import paddle_headwords_core as core
from picture_capture.models import AppSettings
from picture_capture.ocr import column_band_sampling, lemma_parser, source_candidate_coordinates


def _geometry(*, kind="identity"):
    transform = SimpleNamespace(
        kind=kind,
        canonical_size=lambda size: size,
        canonical_box_to_source=lambda box, image_size: (2, 1, 11, 8),
    )
    return SimpleNamespace(
        transform=transform,
        top=1, bottom=8,
        column_starts=[5], column_widths=[11],
        x_at=lambda col, y: 5 + (int(y) % 2),
    )


def _page():
    pixels = np.zeros((10, 20, 3), dtype=np.uint8)
    for y in range(10):
        for x in range(20):
            pixels[y, x] = (x * 5, y * 17, (x + y) * 3)
    return Image.fromarray(pixels, "RGB")


def test_column_unwrap_source_pixels_and_blank_outside():
    image = _page()
    geo = _geometry()
    settings = AppSettings()
    settings.paddle_band_left_margin = 2
    result, top, left = core.unwrap_column_band(
        image, geo, 0, settings, source_width=24,
    )
    assert (result.size, top, left) == ((24, 7), 1, 2)
    actual = np.asarray(result)
    original = np.asarray(image)
    for row in range(7):
        source_y = row + top
        left_x = geo.x_at(0, source_y) - left
        np.testing.assert_array_equal(
            actual[row, :20 - left_x], original[source_y, left_x:],
        )
        assert np.all(actual[row, 20 - left_x:] == 255)
    assert core.unwrap_column_band.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(core.unwrap_column_band).parameters) == [
        "image", "geometry", "column", "settings", "source_width", "source_rgb",
    ]


def test_column_unwrap_precomputed_rgb_and_mismatched_page_fail_closed():
    image = _page()
    geo = _geometry()
    settings = AppSettings()
    original = np.asarray(image)
    direct = core.unwrap_column_band(image, geo, 0, settings, source_width=25)
    cached = core.unwrap_column_band(
        image, geo, 0, settings, source_width=25, source_rgb=original.copy(),
    )
    assert direct[1:] == cached[1:]
    np.testing.assert_array_equal(np.asarray(direct[0]), np.asarray(cached[0]))
    with pytest.raises(ValueError, match="RGB"):
        core.unwrap_column_band(image, geo, 0, settings, source_rgb=np.zeros((10, 20)))
    with pytest.raises(ValueError, match="尺寸"):
        core.unwrap_column_band(image, geo, 0, settings, source_rgb=np.zeros((9, 20, 3)))
    rgba = np.dstack([original, np.zeros((10, 20), dtype=np.uint8)])
    got = core.unwrap_column_band(image, geo, 0, settings, source_width=25, source_rgb=rgba)
    np.testing.assert_array_equal(np.asarray(got[0]), np.asarray(direct[0]))


def test_column_unwrap_transformed_branch_and_live_normalizer(monkeypatch):
    image = _page()
    geo = _geometry(kind="mirror_x")
    settings = AppSettings()
    seen = []
    normalize = core.normalize_page_rgb

    def spy(image_arg):
        seen.append(image_arg)
        return normalize(image_arg)

    monkeypatch.setattr(core, "normalize_page_rgb", spy)
    band, top, margin = core.unwrap_column_band(
        image, geo, 0, settings, source_width=30,
    )
    assert seen and seen[0] is image
    assert top == 1
    assert margin == settings.paddle_band_left_margin
    np.testing.assert_array_equal(
        np.asarray(band), np.asarray(image.crop((2, 1, 11, 8))),
    )


def test_helper_owners_preserve_historical_names_and_behavior():
    for row, expected in ((None, None), ({}, None), ({"source_y": "17"}, 17),
                          ({"_axis_v": "bad", "source_y": 12}, None)):
        assert core._candidate_axis_v(row) == expected
        assert source_candidate_coordinates.candidate_axis_v(row) == expected
    for text, desc, morph, expected in [
        ("Ml", False, False, True), ("II", False, False, True),
        ("L", False, False, True), ("ABBR", False, False, False),
        ("Ml", True, False, False), ("Ml", False, True, False),
    ]:
        parsed = SimpleNamespace(raw=text, has_descriptor=desc, has_inflection=morph)
        assert core._looks_like_marker_noise_lemma(parsed) is expected
    assert core._looks_like_marker_noise_lemma(None) is False
    assert core._looks_like_marker_noise_lemma.__module__ == "picture_capture.paddle_headwords_core"
    assert core._candidate_axis_v.__module__ == "picture_capture.paddle_headwords_core"


def test_round22_single_function_owner_no_hidden_runtime_globals():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(pkg.glob("*.py"))) == 7
    path = pkg / "ocr" / "column_band_sampling.py"
    assert path.is_file()
    assert not (pkg / "column_band_sampling.py").exists()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert [n.name for n in tree.body if isinstance(n, ast.FunctionDef)] == [
        "unwrap_column_band_impl",
    ]
    assert not any(isinstance(n, (ast.Assign, ast.AnnAssign)) for n in tree.body)
    assert callable(lemma_parser.looks_like_marker_noise_lemma)
