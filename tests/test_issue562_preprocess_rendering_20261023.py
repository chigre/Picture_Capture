"""Rendering ownership, live API wiring and real image export contracts."""
from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import pickle
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image, JpegImagePlugin
import pytest

from picture_capture import image_preprocessing as api
from picture_capture.preprocess import rendering

NAMES = ("overlay_excluded_regions", "review_image", "processed_image",
         "processed_image_with_canvas", "save_review_preview", "save_processed_page")


@pytest.fixture
def analysis():
    return api.PreprocessAnalysis(
        source_width=40, source_height=60, correction_angle_deg=0, applied_angle_deg=0,
        crop_box=(4, 6, 34, 56), raw_content_box=(4, 6, 34, 56), text_box=None,
        source_boxes=0, angle_samples=0, angle_mad_deg=0, retained_ratio=.625,
        confidence=1, status="normal", method="test",
    )


@pytest.fixture
def source():
    return Image.fromarray(np.arange(40 * 60 * 3, dtype=np.uint8).reshape(60, 40, 3))


@pytest.mark.parametrize("name", NAMES)
def test_single_owner_and_compatible_callable(name):
    fn = getattr(api, name)
    assert pickle.loads(pickle.dumps(fn)) is fn
    assert Path(getattr(rendering, name).__code__.co_filename) == Path(rendering.__file__)
    defs = {n.name: n for n in ast.parse(Path(api.__file__).read_text()).body
            if isinstance(n, ast.FunctionDef)}
    assert len(defs[name].body) == 1
    assert isinstance(defs[name].body[0], ast.Return)


def test_leaf_import_does_not_initialize_facade_gui_or_paddle():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.preprocess import rendering
assert 'picture_capture.image_preprocessing' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "P"])
@pytest.mark.parametrize("box", [(4, 6, 34, 56), (-20, -30, 80, 90)])
def test_overlay_normalizes_modes_clamps_and_preserves_source(source, mode, box):
    source = source.convert(mode)
    before = source.tobytes()
    result = api.overlay_excluded_regions(source, box)
    assert result.size == source.size and result.mode == "RGB"
    assert result.getpixel((20, 30)) == api.normalize_page_rgb(source).getpixel((20, 30))
    assert source.tobytes() == before


def test_live_render_operations_are_supplied_at_call_time(monkeypatch, source, analysis):
    overlay_adapter = api.overlay_excluded_regions
    corrected = Image.new("RGB", source.size, "red")
    calls = []
    monkeypatch.setattr(api, "geometry_corrected_image", lambda *args: corrected)
    assert api.processed_image(source, analysis).getpixel((0, 0)) == (255, 0, 0)
    monkeypatch.setattr(api, "overlay_excluded_regions", lambda image, box: calls.append((image, box)) or image)
    assert api.review_image(source, analysis) is corrected
    assert calls == [(corrected, analysis.crop_box)]
    monkeypatch.setattr(api, "normalize_page_rgb", lambda image: corrected)
    assert api.overlay_excluded_regions is not rendering.overlay_excluded_regions
    # Restore the adapter to verify the live normalizer as well.
    monkeypatch.setattr(api, "overlay_excluded_regions", overlay_adapter)
    assert api.overlay_excluded_regions(source, analysis.crop_box).getpixel((20, 30)) == (255, 0, 0)


def test_canvas_expands_without_resampling_and_uses_current_factory(monkeypatch, source, analysis):
    content = source.crop(analysis.crop_box)
    canvas = api.output_canvas_info(analysis, enabled=True, canvas_width=70, canvas_height=90,
                                  margin_left=3, margin_right=5, margin_top=7, margin_bottom=9)
    undersized = replace(canvas, width=1, height=1)
    factory = api.output_canvas_info
    calls = []
    monkeypatch.setattr(api, "output_canvas_info", lambda *a, **kw: calls.append(kw) or factory(*a, **kw))
    result = api.processed_image_with_canvas(source, analysis, undersized)
    assert result.size == (38, 66)
    assert calls[0]["canvas_width"] == 38 and calls[0]["canvas_height"] == 66
    assert result.crop((3, 7, 33, 57)).tobytes() == content.tobytes()
    assert result.getpixel((0, 0)) == (255, 255, 255)


@pytest.mark.parametrize("suffix,fmt", [(".PNG", "PNG"), (".jpg", "JPEG"),
                                        (".JPEG", "JPEG"), (".tif", "TIFF"), (".TIFF", "TIFF")])
def test_export_reopens_in_original_coordinates(tmp_path, source, analysis, suffix, fmt):
    page = tmp_path / "scan.png"
    source.save(page)
    destination = tmp_path / "nested" / ("crop" + suffix)
    assert api.save_processed_page(page, analysis, destination) == destination
    with Image.open(destination) as output:
        assert output.format == fmt and output.size == (30, 50)
        if fmt == "JPEG":
            assert JpegImagePlugin.get_sampling(output) == 0
        else:
            assert output.tobytes() == source.crop(analysis.crop_box).tobytes()
        if fmt == "TIFF":
            assert output.info["compression"] == "tiff_lzw"
    with Image.open(page) as original:
        assert original.tobytes() == source.tobytes()


@pytest.mark.parametrize("size,requested,expected", [((80, 100), 10, (80, 100)),
    ((400, 800), 10, (160, 320)), ((400, 800), 600, (300, 600))])
def test_preview_size_floor_and_jpeg_policy(tmp_path, monkeypatch, analysis, size, requested, expected):
    page = tmp_path / "scan.png"
    Image.new("RGB", size, "white").save(page)
    calls = []
    monkeypatch.setattr(api, "review_image", lambda image, a: calls.append(a) or image.copy())
    target = tmp_path / "preview" / "extension.png"
    assert api.save_review_preview(page, analysis, target, max_long_side=requested) == target
    with Image.open(target) as output:
        assert output.format == "JPEG" and output.size == expected
    assert calls == [analysis]


def test_save_uses_current_canvas_renderer(tmp_path, monkeypatch, analysis):
    page = tmp_path / "scan.png"
    Image.new("RGB", (40, 60)).save(page)
    canvas = SimpleNamespace(enabled=True)
    calls = []
    monkeypatch.setattr(api, "processed_image_with_canvas",
        lambda image, a, c: calls.append((a, c)) or Image.new("RGB", (7, 9), "blue"))
    target = tmp_path / "result.png"
    api.save_processed_page(page, analysis, target, canvas=canvas)
    with Image.open(target) as output:
        assert output.size == (7, 9) and output.getpixel((0, 0)) == (0, 0, 255)
    assert calls == [(analysis, canvas)]
