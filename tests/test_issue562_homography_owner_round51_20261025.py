"""Issue #562 Round 51: one physical owner for homography and paper fill."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
import pickle

import numpy as np
import pytest
from PIL import Image

from picture_capture.preprocess import deskew, geometry, homography_ops, orthogonal_dewarp
from picture_capture.preprocess.analysis_image import normalize_page_rgb


ROOT = Path(__file__).resolve().parents[1]


def test_new_operator_owner_is_leaf_only_and_original_entrypoints_are_thin():
    owner = (ROOT / "src/picture_capture/preprocess/homography_ops.py").read_text(encoding="utf-8")
    tree = ast.parse(owner)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert {"solve_quad_homography", "homography_jacobian", "transform_points_homography",
            "transform_polygons_homography", "corner_paper_fill",
            "apply_homography_image"} <= functions.keys()
    assert "picture_capture.app" not in owner
    assert "picture_capture.preprocess.pipeline" not in owner
    assert "tkinter" not in owner
    assert "np.linalg.solve" in owner
    assert "Image.Transform.PERSPECTIVE" in owner
    for module, methods in (
        (geometry, ("homography_jacobian", "_homography", "transform_points_homography",
                    "transform_polygons_homography", "_paper_fill", "apply_homography_image")),
        (deskew, ("_paper_fill",)),
        (orthogonal_dewarp, ("_paper_fill",)),
    ):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "_homography_ops." in source
        nodes = {node.name: node for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef)}
        for method in methods:
            assert method in nodes
            assert len(nodes[method].body) <= 2
            fn = getattr(module, method)
            assert Path(fn.__code__.co_filename).resolve() == Path(module.__file__).resolve()
    assert pickle.loads(pickle.dumps(geometry.transform_points_homography)) is geometry.transform_points_homography


def test_quad_solver_and_jacobian_preserve_numeric_geometry_and_error_policy():
    src = np.asarray([[0, 0], [20, 0], [20, 12], [0, 12]], dtype=float)
    dst = src + np.asarray([3.0, -2.0])
    matrix = geometry._homography(src, dst)
    assert matrix.shape == (3, 3)
    mapped = geometry.transform_points_homography(src, matrix.reshape(-1))
    np.testing.assert_allclose(mapped, dst, atol=1e-9)
    np.testing.assert_allclose(
        geometry.homography_jacobian(matrix.reshape(-1), 8, 6),
        np.eye(2), atol=1e-10,
    )
    with pytest.raises(ValueError, match="four 2D"):
        geometry._homography(src[:3], dst[:3])
    singular = (1, 0, 0, 0, 1, 0, 1, 0, 0)
    with pytest.raises(ValueError, match="singular"):
        geometry.homography_jacobian(singular, 0, 3)


@pytest.mark.parametrize("mode", ("RGB", "RGBA", "P"))
def test_legacy_paper_fill_three_owners_match_corner_median_without_mutating(mode):
    image = Image.new("RGB", (28, 22), (210, 225, 240))
    image.putpixel((0, 0), (40, 80, 120))
    image.putpixel((14, 12), (2, 4, 6))
    if mode == "RGBA":
        image = image.convert("RGBA")
        image.putpixel((0, 0), (255, 0, 0, 0))
    elif mode == "P":
        image = image.quantize(colors=32)
    original = image.tobytes()
    expected = homography_ops.corner_paper_fill(
        image, normalize_page_rgb=normalize_page_rgb,
    )
    assert geometry._paper_fill(image) == deskew._paper_fill(image) == orthogonal_dewarp._paper_fill(image) == expected
    assert image.tobytes() == original


def test_transform_polygons_calls_live_geometry_point_transform(monkeypatch):
    calls = []
    marker = np.asarray([3.0, 4.0])
    def translated(points, matrix):
        calls.append((points.copy(), matrix))
        return points + marker
    monkeypatch.setattr(geometry, "transform_points_homography", translated)
    poly = np.asarray([[2, 3], [7, 3], [7, 9]], dtype=float)
    output = geometry.transform_polygons_homography([poly], (1, 0, 0, 0, 1, 0, 0, 0, 1))
    np.testing.assert_array_equal(output[0], poly + marker)
    np.testing.assert_array_equal(poly, np.asarray([[2, 3], [7, 3], [7, 9]], dtype=float))
    assert len(calls) == 1


def test_homography_image_warp_preserves_source_size_rgb_and_live_paper_callback(monkeypatch):
    image = Image.new("RGBA", (24, 16), (240, 240, 240, 255))
    image.putpixel((10, 7), (250, 20, 30, 255))
    before = image.tobytes()
    identity = (1, 0, 0, 0, 1, 0, 0, 0, 1)
    output = geometry.apply_homography_image(image, identity)
    assert output.mode == "RGB" and output.size == image.size
    assert output.getpixel((10, 7)) == (250, 20, 30)
    assert image.tobytes() == before

    observed = []
    def fake_paper_fill(normalized):
        observed.append(normalized.mode)
        return (1, 2, 3)
    monkeypatch.setattr(geometry, "_paper_fill", fake_paper_fill)
    shifted = (1, 0, 5, 0, 1, 0, 0, 0, 1)
    warped = geometry.apply_homography_image(image, shifted)
    assert observed == ["RGB"]
    assert warped.getpixel((0, 7)) == (1, 2, 3)
    assert warped.getpixel((15, 7)) == (250, 20, 30)


def test_legacy_callable_signatures_and_deskew_pickle_identity():
    assert list(inspect.signature(geometry.apply_homography_image).parameters) == ["image", "matrix"]
    assert list(inspect.signature(geometry.transform_polygons_homography).parameters) == ["polygons", "matrix"]
    assert list(inspect.signature(geometry.homography_jacobian).parameters) == ["matrix", "x", "y"]
    assert list(inspect.signature(deskew._paper_fill).parameters) == ["image"]
    from picture_capture.preprocess import pipeline
    assert pipeline._paper_fill is deskew._paper_fill
    assert pickle.loads(pickle.dumps(deskew._paper_fill)) is deskew._paper_fill
