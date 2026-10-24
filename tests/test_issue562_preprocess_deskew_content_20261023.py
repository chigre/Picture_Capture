"""Preprocessing primitive ownership and source-canvas compatibility contracts."""
from __future__ import annotations

import ast
from dataclasses import replace
import importlib.util
import pickle
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image
import pytest

from picture_capture.preprocess import pipeline as facade
from picture_capture.layout.detection import LayoutEstimate
from picture_capture.models import AppSettings
from picture_capture.preprocess import content_bounds, deskew

SKEW_NAMES = (
    "_normalize_half_turn", "_weighted_median", "estimate_skew_from_polygons",
    "_paper_fill", "deskew_image", "_rotate_point_same_canvas",
    "_rotate_polygons_same_canvas", "_rotated_text_box", "_polygon_boxes",
    "_expand_box_px", "_rotate_box_same_canvas",
)


@pytest.mark.parametrize("name", (*SKEW_NAMES, "_smooth_1d"))
def test_callable_keeps_historical_import_and_pickle_identity(name):
    owner = content_bounds if name == "_smooth_1d" else deskew
    fn = getattr(owner, name)
    assert getattr(facade, name) is fn
    assert fn.__module__ == "picture_capture.preprocess.pipeline"
    assert pickle.loads(pickle.dumps(fn)) is fn
    assert Path(fn.__code__.co_filename).resolve() == Path(owner.__file__).resolve()


def test_facade_only_delegates_content_frames_and_contains_no_primitive_bodies():
    tree = ast.parse(Path(facade.__file__).read_text(encoding="utf-8"))
    definitions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert not (set(SKEW_NAMES) | {"_smooth_1d"}) & definitions.keys()
    for name in ("_projection_content_box", "_layout_content_box_from_polygons", "_projection_skew_fallback"):
        assert len(definitions[name].body) == 1
        assert isinstance(definitions[name].body[0], ast.Return)


@pytest.mark.parametrize("module", ("deskew", "content_bounds"))
def test_leaf_first_import_has_no_facade_gui_or_native_model_initialization(module):
    script = f"""
import importlib, sys
importlib.import_module('picture_capture.preprocess.{module}')
for name in ('picture_capture.preprocess.pipeline', 'picture_capture.app', 'paddle', 'paddleocr'):
    assert name not in sys.modules, name
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)


@pytest.mark.parametrize("mode", ("RGB", "RGBA", "P"))
def test_zero_angle_preserves_source_pixels_without_sharing_storage(mode):
    image = Image.new(mode, (17, 11), "white" if mode == "RGB" else 0)
    if mode == "RGBA":
        image.putpixel((4, 3), (255, 0, 0, 128))
    elif mode == "P":
        image.putpalette([0, 0, 0, 255, 0, 0] + [0, 0, 0] * 254)
        image.info["transparency"] = 0
        image.putpixel((4, 3), 1)
    else:
        image.putpixel((4, 3), (255, 0, 0))
    before = image.tobytes()
    normalized = facade.normalize_page_rgb(image)
    corrected = facade.deskew_image(image, 0)
    assert corrected.size == image.size and corrected.mode == "RGB"
    assert corrected.tobytes() == normalized.tobytes()
    corrected.putpixel((4, 3), (0, 255, 0))
    assert image.tobytes() == before


def test_same_canvas_rotation_preserves_pillow_sign_and_point_identity():
    assert facade._rotate_point_same_canvas(7, 4, 11, 9, 90) == pytest.approx((5, 2))
    assert facade._rotate_point_same_canvas(7, 4, 11, 9, 0) == (7.0, 4.0)
    poly = np.asarray([[1, 2], [7, 2], [7, 6], [1, 6]], dtype=float)
    before = poly.copy()
    rotated = facade._rotate_polygons_same_canvas([poly, np.asarray([1, 2])], 11, 9, 0)
    assert len(rotated) == 1
    np.testing.assert_array_equal(rotated[0], poly)
    rotated[0][0, 0] = 99
    np.testing.assert_array_equal(poly, before)
    assert facade._rotate_box_same_canvas((1, 2, 7, 6), 11, 9, 0) == (1, 2, 7, 6)
    assert facade._expand_box_px((1, 2, 7, 6), 11, 9, 10000) == (0, 0, 11, 9)


def test_projection_wrappers_use_current_facade_mask_and_reject_blank(monkeypatch):
    image = Image.new("RGB", (100, 80), "white")
    settings = AppSettings()
    calls = []

    def mask(gray, actual_settings):
        assert actual_settings is settings
        calls.append(gray.shape)
        ink = np.zeros(gray.shape, dtype=bool)
        ink[20:60, 30:70] = True
        return ink

    monkeypatch.setattr(facade, "analysis_ink_mask", mask)
    box = facade._projection_content_box(image, settings)
    assert 20 <= box[0] <= 30 and 70 <= box[2] <= 80
    assert calls == [(80, 100)]
    assert isinstance(facade._projection_skew_fallback(image, settings, writing_mode="vertical-rl"), float)
    assert len(calls) == 2
    monkeypatch.setattr(facade, "analysis_ink_mask", lambda gray, _: np.zeros(gray.shape, dtype=bool))
    with pytest.raises(RuntimeError, match="未检测到足够的页面墨迹"):
        facade._projection_content_box(image, settings)
    assert image.tobytes() == Image.new("RGB", image.size, "white").tobytes()


def test_layout_wrapper_passes_current_estimator_and_keeps_header_and_last_column(monkeypatch):
    settings = AppSettings(layout_columns_policy="fixed", columns=2)
    polygons = [np.asarray([(x, y), (r, y), (r, b), (x, b)], dtype=float)
                for x, y, r, b in ((20, 5, 35, 10), (10, 20, 40, 26),
                                    (60, 20, 90, 26), (10, 50, 40, 56))]
    estimate = LayoutEstimate(columns=2, start_y=20, column_width=30, gutter=20,
                              manual_x=10, bottom_y=75, character_height=6,
                              row_padding=0, source_boxes=4,
                              column_starts=(10, 60), column_rights=(40, 90))
    calls = []

    def infer(boxes, size, **kwargs):
        calls.append((boxes, size, kwargs))
        return estimate

    monkeypatch.setattr(facade, "infer_layout_from_boxes", infer)
    box, returned = facade._layout_content_box_from_polygons(polygons, 100, 80, settings)
    assert returned is estimate and box == (10, 5, 90, 75)
    assert calls[0][1] == (100, 80)
    assert calls[0][2] == dict(display_scale=1.0, ink_mask=None, columns_policy="fixed",
                              fixed_columns=2, column_separator_mode=settings.layout_column_separator_mode)
    monkeypatch.setattr(facade, "infer_layout_from_boxes", lambda *_a, **_k: replace(estimate, column_rights=(40, 94)))
    assert facade._layout_content_box_from_polygons(polygons, 100, 80, settings)[0] == (10, 5, 94, 75)
    with pytest.raises(RuntimeError, match="文本框过少"):
        facade._layout_content_box_from_polygons(polygons[:3], 100, 80, settings)


def test_preprocessing_size_guard_normalizes_crlf_and_still_rejects_growth(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    path = repo / "scripts/architecture_guard.py"
    spec = importlib.util.spec_from_file_location("preprocess_architecture_guard", path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    source_path = Path(facade.__file__).resolve()
    canonical = source_path.read_text(encoding="utf-8").encode("utf-8")
    windows = tmp_path / "preprocess/pipeline.py"
    windows.parent.mkdir(parents=True, exist_ok=True)
    windows.write_bytes(canonical.replace(b"\n", b"\r\n"))
    assert windows.stat().st_size > guard.MAX_PREPROCESS_FACADE_BYTES
    assert guard._normalized_source_size(windows) == len(canonical) <= guard.MAX_PREPROCESS_FACADE_BYTES
    original = guard._normalized_source_size
    reads = []

    def normalized(path):
        if path.resolve() == source_path:
            reads.append(path)
            return original(windows)
        return original(path)

    monkeypatch.setattr(guard, "_normalized_source_size", normalized)
    assert guard.collect_violations() == []
    assert len(reads) >= 2  # Oversized baseline and the new extraction ratchet.
    # The moved pipeline is shorter, so fixed-size synthetic growth can stay
    # below the unchanged limit. Always cross the actual byte ceiling.
    growth = b"# actual source growth"
    extra = (guard.MAX_PREPROCESS_FACADE_BYTES - len(canonical)) // len(growth) + 2
    windows.write_bytes(canonical + growth * extra)
    assert any("preprocessing facade regressed beyond extracted owners" in v for v in guard.collect_violations())
