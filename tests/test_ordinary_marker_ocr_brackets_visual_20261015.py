"""Regression for marked-entry OCR cleanup and role-independent large heads.

Synthetic scans only: no private page pixels, PDIC rewrites or real OCR model.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from picture_capture.entry_classification import (
    get_entry_classification, register_entry_classification,
)
from picture_capture.entry_ocr_crop import (
    EntryOcrRowMetrics, entry_ocr_crop_box,
)
from picture_capture.entry_ocr_visual_scale import visual_oversized_head_height
from picture_capture.layout_transform import LayoutTransform
from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_marker_ocr_text import bracketed_ocr_lemma
from picture_capture.processing_core import _ordinary_marker_local_crop


@pytest.mark.parametrize(("raw", "expected"), [
    ("前面乱字【蘋果】後面釋義", "蘋果"),
    ("1.【蘋 果】意思", "蘋果"),
    ("前面文字【蘋果", "蘋果"),
    ("蘋果】後面釋義", "蘋果"),
    ("前面文字 蘋果】後面釋義", "蘋果"),
    ("【雲端服務】描述", "雲端服務"),
    ("甲【一刀切】释义", "一刀切"),
    ("甲\n【第二行】", None),
    ("無符號正常詞頭", None),
    ("【】空括號", None),
    ("【English】detail", None),
    ("【詞頭】解釋", "詞頭"),
])
def test_cjk_bracket_boundaries_are_independent_and_bounded(raw, expected):
    assert bracketed_ocr_lemma(raw, enabled=True) == expected
    assert bracketed_ocr_lemma(raw, enabled=False) is None


def test_unclosed_bracket_does_not_swallow_explanatory_tail():
    assert bracketed_ocr_lemma("雜文【蘋果 pronunciation n.", enabled=True) == "蘋果"
    assert bracketed_ocr_lemma("【" + "長" * 35 + "】", enabled=True) is None
    assert bracketed_ocr_lemma("【" + "長" * 35, enabled=True) == "長" * 24


class _Geometry:
    def __init__(self, image: Image.Image):
        self.transform = LayoutTransform("identity")
        self.source_size = image.size
        self.column_starts = [100, 500]
        self.column_widths = [300, 300]

    def source_to_canonical(self, x, y):
        return int(x), int(y)

    def x_at(self, col, v):
        return self.column_starts[col]


def _settings(**changes):
    opts = dict(
        ocr_language="chi_tra", dictionary_profile_id="cjk_visual",
        layout_writing_mode="horizontal-tb", character_height=40,
        row_padding=12, right_ratio=100,
        profile_cjk_allow_single_headword=True,
    )
    opts.update(changes)
    return AppSettings(**opts)


def _page_with_large_head():
    image = Image.new("RGB", (850, 580), "white")
    paint = ImageDraw.Draw(image)
    paint.rectangle((155, 201, 248, 300), fill="black")  # 2.5x row height
    paint.rectangle((104, 209, 113, 222), fill="black")  # numbering prefix
    return image


def test_manual_regular_role_still_crops_full_large_glyph_for_ocr():
    image = _page_with_large_head()
    geometry = _Geometry(image)
    entry = Entry("", 100, 200)
    register_entry_classification(
        entry, entry_source="manual", entry_scale="regular",
    )
    settings = _settings()
    metrics = EntryOcrRowMetrics(40.0, 52.0)
    visual_height = visual_oversized_head_height(
        image, entry, geometry, settings, line_height=metrics.line_height,
    )
    assert visual_height >= 100
    cropped = entry_ocr_crop_box(
        entry, geometry, settings, image.size,
        row_metrics=metrics, visual_head_height=visual_height,
    )
    regular_box = entry_ocr_crop_box(
        entry, geometry, settings, image.size, row_metrics=metrics,
    )
    assert regular_box[3] < 300
    assert cropped[3] >= 300
    actual, is_large = _ordinary_marker_local_crop(
        image, entry, geometry, settings,
        row_metrics=metrics, source_image=image,
    )
    assert is_large is True
    assert actual.height == cropped[3] - cropped[1]
    assert get_entry_classification(entry).entry_scale == "regular"
    assert (entry.x, entry.y) == (100, 200)


def test_oversized_image_at_other_column_does_not_change_local_regular_crop():
    image = _page_with_large_head()
    entry = Entry("", 500, 200)
    geometry = _Geometry(image)
    settings = _settings()
    assert not visual_oversized_head_height(
        image, entry, geometry, settings, line_height=40,
    )


def test_plain_small_text_rows_and_latin_profile_do_not_expand():
    image = Image.new("RGB", (850, 580), "white")
    p = ImageDraw.Draw(image)
    p.rectangle((104, 202, 125, 221), fill="black")
    p.rectangle((104, 252, 125, 271), fill="black")
    entry = Entry("", 100, 200)
    geom = _Geometry(image)
    assert visual_oversized_head_height(
        image, entry, geom, _settings(), line_height=40,
    ) == 0
    assert visual_oversized_head_height(
        _page_with_large_head(), entry, geom,
        _settings(profile_cjk_allow_single_headword=False),
        line_height=40,
    ) == 0


def test_marker_ocr_and_preview_use_identical_role_independent_visual_extent():
    from pathlib import Path
    base = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    source = (base / "processing_core.py").read_text("utf-8")
    preview = (base / "ocr_crop_preview_ui.py").read_text("utf-8")
    for content in (source, preview):
        assert "visual_oversized_head_height(" in content
        assert "visual_head_height=visual_height," in content
    assert "large_for_ocr = meta.entry_scale == \"oversized\" or visual_height > 0" in source
