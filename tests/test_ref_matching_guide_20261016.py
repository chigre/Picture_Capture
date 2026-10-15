"""REF cross-page guide recognition and right-offset target geometry."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.ref_box_detection import (
    add_ref_sample, match_ref_templates, ref_box_after_guide,
    default_ref_box_dimensions, detect_ref_boxes_page,
)
from picture_capture.ref_boxes import RefBox, read_ref_boxes, write_ref_boxes
from picture_capture.ui.settings.lifecycle import validate_ref_box_controls


def test_auto_ref_starts_after_guide_width_and_uses_manual_size():
    settings = AppSettings(
        character_height=16, row_padding=4,
        ref_box_width_lines=2, ref_box_height_lines=1,
    )
    assert default_ref_box_dimensions(settings) == (40, 20)
    assert ref_box_after_guide((40, 30, 28, 14), (180, 120), settings) == (
        68, 27, 40, 20,
    )
    # No wrap into the following column/page if guide ends at right edge.
    assert ref_box_after_guide((169, 30, 12, 14), (180, 120), settings) is None
    assert ref_box_after_guide((145, 30, 25, 14), (180, 120), settings) == (
        170, 27, 10, 20,
    )


def _guide_page(page: Path, patch: np.ndarray, *, x: int, y: int,
                width: int = 260, height: int = 150) -> None:
    image = np.full((height, width, 3), 245, dtype=np.uint8)
    patch_h, patch_w = patch.shape[:2]
    image[y:y + patch_h, x:x + patch_w] = patch
    Image.fromarray(image).save(page)


def test_guidance_sample_creates_ref_after_not_over_sample(tmp_path):
    page = tmp_path / "sampled.png"
    rng = np.random.default_rng(45)
    guide = rng.integers(20, 195, (20, 44), dtype=np.uint8)
    patch = np.stack((guide, guide, guide), axis=2)
    _guide_page(page, patch, x=42, y=32)
    sample = add_ref_sample(page, (42, 32, 86, 52))
    with Image.open(page) as im:
        hits = match_ref_templates(im, [sample], threshold=0.96,
                                   scale_tolerance_percent=0)
    assert (42, 32, 44, 20) in hits
    settings = AppSettings(
        character_height=18, row_padding=4,
        ref_box_width_lines=2, ref_box_height_lines=1,
        ref_match_threshold=0.96, ref_match_scale_tolerance_percent=0,
    )
    result = detect_ref_boxes_page(page, settings, 0)
    assert result["status"] == "changed"
    assert result["added"] == 1
    assert read_ref_boxes(page) == [
        RefBox(1, 86, 31, 44, 22, None, ""),
    ]
    assert detect_ref_boxes_page(page, settings, 0)["added"] == 0


def test_manual_boxes_are_never_overwritten_by_offset_auto_ref(tmp_path):
    page = tmp_path / "manual.png"
    rng = np.random.default_rng(46)
    grayscale = rng.integers(20, 195, (20, 44), dtype=np.uint8)
    patch = np.stack([grayscale] * 3, axis=2)
    _guide_page(page, patch, x=42, y=32)
    add_ref_sample(page, (42, 32, 86, 52))
    manual = RefBox(7, 86, 31, 44, 22, 0, "人工已填")
    write_ref_boxes(page, [manual], expected_ticket=None)
    settings = AppSettings(
        character_height=18, row_padding=4, ref_box_width_lines=2,
        ref_match_threshold=0.96, ref_match_scale_tolerance_percent=0,
    )
    assert detect_ref_boxes_page(page, settings, 0)["added"] == 0
    assert read_ref_boxes(page) == [manual]


def test_cross_page_scale_and_tint_recognition_without_opencv(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "cv2", None)
    source_page = tmp_path / "source.png"
    target_page = tmp_path / "target.png"
    rng = np.random.default_rng(20261016)
    glyph = rng.integers(20, 210, (24, 48), dtype=np.uint8)
    initial = np.repeat(glyph[:, :, None], 3, axis=2)
    _guide_page(source_page, initial, x=33, y=22)
    sample = add_ref_sample(source_page, (33, 22, 81, 46))

    # 17% larger, globally brighter and warmer scanned guide word.
    # RGB exact matching is brittle here; contrast-normalized grayscale
    # with multiple sizes should still recognize the local shape.
    resized = Image.fromarray(initial).resize((56, 28), Image.Resampling.BILINEAR)
    resized_array = np.asarray(resized).astype(np.float32)
    warmer = np.clip(resized_array * 0.72 + np.array([62, 54, 40]), 0, 255)
    _guide_page(target_page, warmer.astype(np.uint8), x=94, y=43, width=280, height=180)

    with Image.open(target_page) as im:
        matches = match_ref_templates(
            im, [sample], threshold=0.84, scale_tolerance_percent=25.0,
        )
    assert any(abs(x - 94) <= 2 and abs(y - 43) <= 2
               and abs(w - 56) <= 2 and abs(h - 28) <= 2
               for x, y, w, h in matches)

    settings = AppSettings(
        character_height=18, row_padding=4, ref_box_width_lines=2,
        ref_match_threshold=0.84, ref_match_scale_tolerance_percent=25,
    )
    outcome = detect_ref_boxes_page(target_page, settings, 0)
    assert outcome["status"] == "changed"
    assert outcome["added"] >= 1
    boxes = read_ref_boxes(target_page)
    assert any(abs(b.x - 150) <= 3 and abs(b.y - 46) <= 3 and b.w == 44
               for b in boxes)
    # Running again must not duplicate accepted automatic annotations.
    assert detect_ref_boxes_page(target_page, settings, 0)["added"] == 0




def test_minor_anisotropic_page_stretch_can_match_sample_without_cv2(tmp_path, monkeypatch):
    """Slight spine/page curvature can stretch X and compress Y unequally."""
    monkeypatch.setitem(sys.modules, "cv2", None)
    page_a = tmp_path / "a.png"
    page_b = tmp_path / "b.png"
    rng = np.random.default_rng(212)
    pattern = rng.integers(24, 220, (24, 48), dtype=np.uint8)
    rgb = np.stack([pattern] * 3, axis=2)
    _guide_page(page_a, rgb, x=20, y=20)
    sample = add_ref_sample(page_a, (20, 20, 68, 44))
    warped = np.asarray(
        Image.fromarray(rgb).resize((52, 22), Image.Resampling.BILINEAR),
        dtype=np.uint8,
    )
    _guide_page(page_b, warped, x=92, y=41)
    with Image.open(page_b) as img:
        hits = match_ref_templates(
            img, [sample], threshold=0.85,
            scale_tolerance_percent=25,
        )
    assert any(abs(x-92) <= 2 and abs(y-41) <= 2
               and abs(w-52) <= 2 and abs(h-22) <= 2
               for x, y, w, h in hits)


@pytest.mark.parametrize("value", ["-1", "51", "nan", "invalid"])
def test_ref_match_scale_tolerance_rejected_before_settings_mutation(value):
    from types import SimpleNamespace
    with pytest.raises(ValueError):
        validate_ref_box_controls({
            "ref_match_scale_tolerance_percent": SimpleNamespace(
                get=lambda val=value: val,
            ),
        })


def test_match_scale_tolerance_and_button_options_are_persisted(tmp_path):
    settings = AppSettings(
        ref_match_scale_tolerance_percent=35,
        ref_box_action_position="above_left",
        ref_box_delete_always_visible=True,
    )
    path = tmp_path / "settings.json"
    settings.to_json(path)
    reopened = AppSettings.from_json(path)
    assert reopened.ref_match_scale_tolerance_percent == 35
    assert reopened.ref_box_action_position == "above_left"
    assert reopened.ref_box_delete_always_visible is True
