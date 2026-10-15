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



@pytest.mark.parametrize(("ocr_text", "expected"), [
    ("編號【蘋果】字義", "蘋果"),
    ("4【禾王】太平天国天王洪秀全自称。《太平天国·十", "禾王"),
    ("噪音【雲端", "雲端"),
    ("蘋果】其他內容", "蘋果"),
    ("正常文字", "正常文字"),
])
def test_existing_marker_ocr_fallback_applies_profile_bracket_extraction(
    monkeypatch, ocr_text, expected,
):
    """Exercise the real ordinary-marker OCR writer with OCR engines mocked."""
    from picture_capture import processing_core, ocr_channel, dictionary_profile
    from picture_capture import entry_ocr_crop, paddle_headwords

    image = Image.new("RGB", (850, 580), "white")
    geometry = _Geometry(image)
    settings = _settings(ocr_replace=False)
    entry = Entry("", 100, 200)
    before = (entry.x, entry.y)
    monkeypatch.setattr(
        processing_core, "_page_geometry_context",
        lambda page, cfg, index: (image, settings, image, geometry),
    )
    monkeypatch.setattr(
        processing_core, "sort_entries_reading_order",
        lambda entries, _geometry, _sections: entries,
    )
    monkeypatch.setattr(
        entry_ocr_crop, "resolve_entry_ocr_row_metrics",
        lambda *_args, **_kwargs: EntryOcrRowMetrics(40.0, 52.0),
    )
    monkeypatch.setattr(
        dictionary_profile, "effective_project_profile_id",
        lambda *_args: "cjk_visual",
    )
    monkeypatch.setattr(
        dictionary_profile, "load_dictionary_profile",
        lambda *_args, **_kwargs: SimpleNamespace(
            uses_parser=lambda mode: mode == "cjk_bracketed",
        ),
    )
    monkeypatch.setattr(paddle_headwords, "parse_headword_text", lambda *_args, **_kwargs: None)

    class Channel:
        def __init__(self, _settings):
            pass

        def recognize_crop(self, _image, **_kwargs):
            return SimpleNamespace(
                plan=object(),
                candidates=[SimpleNamespace(
                    ok=True, engine="tesseract", text=ocr_text,
                    confidence=0.91, records=[],
                )],
            )

    monkeypatch.setattr(ocr_channel, "OcrChannelSession", Channel)
    monkeypatch.setattr(
        ocr_channel, "choose_ocr_text",
        lambda _plan, choices: (choices[0], True) if choices else (None, False),
    )
    entries, stats = processing_core.ocr_existing_entry_words_from_markers(
        image, [entry], settings, [], only_blank=True,
    )
    assert entries[0] is entry
    assert entry.word == expected
    assert (entry.x, entry.y) == before
    assert stats["filled"] == 1


def test_latin_or_profile_disabled_marker_ocr_does_not_cut_bracket_words(monkeypatch):
    from picture_capture import processing_core
    # Direct pure-helper check is the stable policy contract; real OCR writer
    # enables this only for explicitly configured CJK-bracket dictionary mode.
    assert bracketed_ocr_lemma("prefix【apple】suffix", enabled=False) is None
    source = __import__("inspect").getsource(processing_core.ocr_existing_entry_words_from_markers)
    assert 'profile.uses_parser("cjk_bracketed")' in source
    assert 'profile_cjk_allow_bracketed_headword' in source



def test_explicit_only_ocr_overwrites_previous_result_clears_failed_and_keeps_manual(monkeypatch):
    """User-triggered pure OCR must replace auto text, not act as blank-fill."""
    from picture_capture import processing_core, ocr_channel, dictionary_profile
    from picture_capture import entry_ocr_crop

    image = Image.new("RGB", (850, 580), "white")
    settings = _settings(ocr_replace=False)
    geometry = _Geometry(image)
    entries = [
        Entry("4【禾王】太平天国天王洪秀全自称", 100, 100,
              ocr_source="ordinary_marker:tesseract"),
        Entry("上次OCR錯誤", 100, 200, ocr_source="ordinary_marker:tesseract"),
        Entry("人工核對", 100, 300, manually_selected=True),
    ]
    before = [(e.x, e.y) for e in entries]
    monkeypatch.setattr(
        processing_core, "_page_geometry_context",
        lambda *_args: (image, settings, image, geometry),
    )
    monkeypatch.setattr(
        processing_core, "sort_entries_reading_order",
        lambda items, *_args: items,
    )
    monkeypatch.setattr(
        entry_ocr_crop, "resolve_entry_ocr_row_metrics",
        lambda *_args, **_kwargs: EntryOcrRowMetrics(40.0, 52.0),
    )
    monkeypatch.setattr(
        dictionary_profile, "effective_project_profile_id",
        lambda *_args: "cjk_visual",
    )
    monkeypatch.setattr(
        dictionary_profile, "load_dictionary_profile",
        lambda *_args, **_kwargs: SimpleNamespace(
            uses_parser=lambda mode: mode == "cjk_bracketed",
        ),
    )

    class Channel:
        calls = 0

        def __init__(self, _settings):
            pass

        def recognize_crop(self, _crop, **_kwargs):
            Channel.calls += 1
            ok = Channel.calls == 1
            return SimpleNamespace(
                plan=object(),
                candidates=[SimpleNamespace(
                    ok=ok, engine="tesseract",
                    text="4【禾王】太平天国" if ok else "",
                    confidence=0.96 if ok else None, records=[],
                )],
            )

    monkeypatch.setattr(ocr_channel, "OcrChannelSession", Channel)
    monkeypatch.setattr(
        ocr_channel, "choose_ocr_text",
        lambda _plan, choices: (choices[0], True) if choices else (None, False),
    )
    changed, stats = processing_core.ocr_existing_entry_words_from_markers(
        image, entries, settings, [], only_blank=False,
    )
    assert [e.word for e in changed] == ["禾王", "", "人工核對"]
    assert changed[1].ocr_source == ""
    assert changed[1].confidence is None
    assert [(e.x, e.y) for e in changed] == before
    assert stats["filled"] == 1
    assert stats["failed"] == 1
    assert stats["skipped_existing"] == 0
    assert stats["skipped_manual"] == 1
    assert Channel.calls == 2


def test_explicit_only_ocr_button_uses_overwrite_not_combined_blank_fill():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "app.py"
    ).read_text("utf-8")
    body = source.split("def ocr_ordinary_lines_text_selected_scope(", 1)[1].split(
        "\n    def run_combined_draw_action(", 1,
    )[0]
    assert "only_blank=False," in body
    assert "only_blank=True," not in body
    assert "if bool(entry.manually_selected)" in body
    assert "OCR文字意外覆盖了人工选定文本" in body
    assert "重新 OCR 并覆盖已有的自动 OCR 文本" in body
    # Automatic combined rescue remains blank-only, as before.
    combined = source.split("    def _detect_pages(", 1)[1]
    assert "only_blank=True," in combined
