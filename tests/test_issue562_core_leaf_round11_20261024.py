"""Issue #562: image-only OCR boundary candidates and single-line PIL crop boxes."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
from picture_capture import processing as public_processing
from picture_capture import processing_core as pc
from picture_capture import paddle_headwords as public_paddle
from picture_capture import paddle_headwords_core as ph
from picture_capture.crop import line_box_geometry
from picture_capture.ocr import image_separator_geometry
from picture_capture.ocr.headword_models import OCRLine, OCRRecord
from picture_capture.models import Entry

PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def _geometry():
    return SimpleNamespace(
        column_starts=[20, 120], column_widths=[80, 80],
        column_paths=[],
        source_size=(240, 180),
        source_to_canonical=lambda x, y: (x, y),
        x_at=lambda i, v: 20 + 100 * i,
        transform=SimpleNamespace(
            canonical_size=lambda s: s,
            canonical_box_to_source=lambda box, size: box,
        ),
    )


def _ocr_settings():
    return SimpleNamespace(
        paddle_separator_column_margin=0,
        paddle_separator_roi_width_ratio=100.0,
        paddle_separator_safety_px=2,
    )


def _gray():
    gray = np.full((100, 80), 255, dtype=np.uint8)
    gray[10:17, 4:68] = 0
    gray[39:47, 4:68] = 0
    gray[77:85, 4:68] = 0
    return gray


def test_paths_signatures_root_inventory_and_model_identity():
    assert len(list(PKG.glob("*.py"))) == 7
    assert (PKG / "crop/line_box_geometry.py").is_file()
    assert (PKG / "ocr/image_separator_geometry.py").is_file()
    assert not (PKG / "line_box_geometry.py").exists()
    assert not (PKG / "image_separator_geometry.py").exists()
    for fn in (pc.clamp_box, pc.line_box):
        assert fn.__module__ == "picture_capture.processing_core"
    for fn in (ph.detect_image_separator_candidates, ph.match_ocr_lines_to_image_boundaries):
        assert fn.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(pc.line_box).parameters) == ["entry", "geometry", "image", "settings"]
    assert list(inspect.signature(ph.detect_image_separator_candidates).parameters) == [
        "gray", "reference_line_height", "settings", "pixel_scale", "lower_bound",
    ]
    assert ph.OCRLine is OCRLine
    assert OCRLine.__module__ == "picture_capture.paddle_headwords_core"


def test_line_crop_half_open_box_and_original_live_hooks(monkeypatch):
    img = Image.new("RGB", (240, 180), "white")
    geo = _geometry()
    entry = Entry(word="word", x=30, y=60)
    settings = SimpleNamespace(row_padding=5, character_height=20, crop_width_percent=80)
    wanted = (10, 55, 84, 85)
    assert pc.line_box(entry, geo, img, settings) == wanted
    assert line_box_geometry.line_box(
        entry, geo, img, settings,
        column_fn=pc.column_index, source_px_fn=pc._source_px, clamp_fn=pc.clamp_box,
    ) == wanted
    original_col = pc.column_index
    monkeypatch.setattr(public_processing, "column_index", lambda *args: 1)
    assert pc.line_box(entry, geo, img, settings) == (110, 55, 184, 85)
    monkeypatch.setattr(public_processing, "column_index", original_col)
    original_px = pc._source_px
    monkeypatch.setattr(public_processing, "_source_px", lambda val: int(val) + 2)
    assert pc.line_box(entry, geo, img, settings) == (10, 53, 84, 89)
    monkeypatch.setattr(public_processing, "_source_px", original_px)


def test_line_box_clamp_and_public_patch(monkeypatch):
    img = Image.new("RGB", (9, 7), "white")
    assert pc.clamp_box((-20, 3, 500, 500), img) == (0, 3, 9, 7)
    assert pc.clamp_box((15, 20, 30, 50), img) == (8, 6, 9, 7)
    assert pc.clamp_box((15, 20, 30, 50), img) == line_box_geometry.clamp_box((15, 20, 30, 50), img)
    image = Image.new("RGB", (240, 180), "white")
    original = pc.clamp_box
    calls = []
    def patched(box, image):
        calls.append(box)
        return original(box, image)
    monkeypatch.setattr(public_processing, "clamp_box", patched)
    assert pc.line_box(
        Entry(word="a", x=30, y=60), _geometry(), image,
        SimpleNamespace(row_padding=5, character_height=20, crop_width_percent=80),
    ) == (10, 55, 84, 85)
    assert len(calls) == 1
    monkeypatch.setattr(public_processing, "clamp_box", original)


def test_image_candidates_and_mutual_pairing_parity():
    gray, settings = _gray(), _ocr_settings()
    candidates = ph.detect_image_separator_candidates(gray, 20, settings)
    direct = image_separator_geometry.detect_image_separator_candidates(
        gray, 20, settings,
        roi_fn=ph._separator_analysis_x_bounds,
        otsu_fn=ph._otsu_threshold,
        runs_fn=ph._true_runs,
    )
    assert candidates == direct
    assert candidates
    assert all("ink_onset_y" in item and "strength" in item for item in candidates)
    lines = [
        OCRLine("first", 0.9, (4, 39, 60, 47), [OCRRecord("first", 0.9, (4, 39, 60, 47))]),
        OCRLine("next", 0.8, (4, 77, 60, 85), [OCRRecord("next", 0.8, (4, 77, 60, 85))]),
    ]
    matches = ph.match_ocr_lines_to_image_boundaries(lines, candidates, 20)
    assert matches == image_separator_geometry.match_ocr_lines_to_image_boundaries(lines, candidates, 20)
    assert all(row["match_method"] == "mutual_nearest_y" for row in matches.values())
    assert ph.match_ocr_lines_to_image_boundaries([], candidates, 20) == {}


def test_image_boundaries_use_live_visual_hooks(monkeypatch):
    gray, settings = _gray(), _ocr_settings()
    original_runs = ph._true_runs
    monkeypatch.setattr(public_paddle, "_true_runs", lambda values: [])
    assert ph.detect_image_separator_candidates(gray, 20, settings) == []
    monkeypatch.setattr(public_paddle, "_true_runs", original_runs)
    original_roi = ph._separator_analysis_x_bounds
    monkeypatch.setattr(public_paddle, "_separator_analysis_x_bounds", lambda *args: (0, 4))
    assert ph.detect_image_separator_candidates(gray, 20, settings) == []
    monkeypatch.setattr(public_paddle, "_separator_analysis_x_bounds", original_roi)
