"""Regression for OCR text orientation after ordinary line drawing.

The scanned text pixels must reach OCR in source/native left-to-right order
even if Layout needed a mirrored or rotated canonical coordinate space.
"""
from __future__ import annotations

from types import SimpleNamespace
from PIL import Image, ImageDraw, ImageOps
from picture_capture.entry_ocr_crop import EntryOcrRowMetrics, entry_ocr_crop_box
from picture_capture.layout_transform import LayoutTransform
from picture_capture.models import AppSettings, Entry
from picture_capture.processing_core import _ordinary_marker_local_crop


def _geometry(transform, source, canonical):
    """A column in canonical coordinates mapped to source-space marker XY."""
    left = 16
    width = min(110, canonical.width - 20)
    return SimpleNamespace(
        transform=transform,
        source_size=source.size,
        column_starts=[left],
        column_widths=[width],
        source_to_canonical=lambda x, y:
            transform.source_to_canonical_point(x, y, source.size),
        x_at=lambda col, v: left,
    )


def _asymmetric_source():
    page = Image.new("RGB", (240, 180), "white")
    pen = ImageDraw.Draw(page)
    # Asymmetric red/green blocks make reversal/rotation testable without
    # depending on an OCR engine, downloaded models, or fonts.
    pen.rectangle((161, 60, 176, 80), fill="#b91c1c")
    pen.rectangle((184, 60, 218, 74), fill="#166534")
    pen.rectangle((196, 83, 201, 93), fill="#1d4ed8")
    return page


def test_horizontal_source_crop_never_mirrors_asymmetric_print():
    source = _asymmetric_source()
    transform = LayoutTransform("mirror_x")
    canonical = transform.canonical_image_for_analysis(source)
    geometry = _geometry(transform, source, canonical)
    entry = Entry("", x=199, y=57)
    settings = AppSettings(
        layout_writing_mode="horizontal-tb",
        layout_text_direction="ltr", layout_transform="mirror_x",
        right_ratio=100, character_height=38, row_padding=1, gutter=0,
    )
    metrics = EntryOcrRowMetrics(38, 48)
    box = entry_ocr_crop_box(
        entry, geometry, settings, canonical.size, row_metrics=metrics,
    )
    expected_box = transform.canonical_box_to_source(box, source.size)
    result, large = _ordinary_marker_local_crop(
        canonical, entry, geometry, settings,
        row_metrics=metrics, source_image=source,
    )
    assert result.size == source.crop(expected_box).size
    assert result.tobytes() == source.crop(expected_box).tobytes()
    assert result.tobytes() != canonical.crop(box).tobytes()
    assert ImageOps.mirror(result).tobytes() == canonical.crop(box).tobytes()
    assert not large


def test_horizontal_source_crop_undoes_accidental_canonical_90_degree_rotation():
    source = _asymmetric_source()
    transform = LayoutTransform("rotate_ccw90")
    canonical = transform.canonical_image_for_analysis(source)
    geometry = _geometry(transform, source, canonical)
    entry = Entry("", x=194, y=63)
    settings = AppSettings(
        layout_writing_mode="horizontal-tb", layout_transform="rotate_ccw90",
        right_ratio=100, character_height=40, row_padding=1, gutter=0,
    )
    metrics = EntryOcrRowMetrics(40, 47)
    box = entry_ocr_crop_box(
        entry, geometry, settings, canonical.size, row_metrics=metrics,
    )
    expected = source.crop(transform.canonical_box_to_source(box, source.size))
    result, large = _ordinary_marker_local_crop(
        canonical, entry, geometry, settings,
        row_metrics=metrics, source_image=source,
    )
    assert result.size == expected.size
    assert result.tobytes() == expected.tobytes()
    assert not large


def test_vertical_crop_keeps_legacy_canonical_ocr_contract():
    source = _asymmetric_source()
    transform = LayoutTransform("rotate_ccw90")
    canonical = transform.canonical_image_for_analysis(source)
    geometry = _geometry(transform, source, canonical)
    entry = Entry("", x=194, y=63)
    settings = AppSettings(
        layout_writing_mode="vertical-rl", layout_transform="rotate_ccw90",
        right_ratio=100, character_height=40, row_padding=1, gutter=0,
    )
    metrics = EntryOcrRowMetrics(40, 47)
    expected_box = entry_ocr_crop_box(
        entry, geometry, settings, canonical.size, row_metrics=metrics,
    )
    actual, _large = _ordinary_marker_local_crop(
        canonical, entry, geometry, settings,
        row_metrics=metrics, source_image=source,
    )
    assert actual.tobytes() == canonical.crop(expected_box).tobytes()


def test_horizontal_source_native_crop_preserves_marker_location():
    source = _asymmetric_source()
    transform = LayoutTransform("identity")
    geometry = _geometry(transform, source, source)
    entry = Entry("", x=24, y=57)
    before = (entry.x, entry.y, entry.word)
    settings = AppSettings(layout_writing_mode="horizontal-tb")
    actual, _ = _ordinary_marker_local_crop(
        source, entry, geometry, settings,
        row_metrics=EntryOcrRowMetrics(38, 48),
        source_image=source,
    )
    assert actual.width > 0 and actual.height > 0
    assert (entry.x, entry.y, entry.word) == before
