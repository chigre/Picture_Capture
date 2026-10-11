"""Regression guards for independent print evidence observed in real scan packs.

Synthetic pages reproduce measured glyph dimensions from annotated originals;
copyrighted dictionary scans remain outside the repository. Full source-image
pixel audits are documented separately.
"""
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_bracket_pair import recover_bracketed_ordinary_entries
from picture_capture.ordinary_crossing_separator import (
    adjust_page_coherent_crossing_separators,
)
from picture_capture.ordinary_independent_indent_rescue import (
    recover_depleted_indent_columns,
)


def _bracket_pair(draw, x, y, *, height, width, span):
    for closing, base in ((False, x), (True, x + span)):
        if closing:
            draw.rectangle((base + width - 7, y, base + width - 1, y + height), fill=0)
            draw.polygon([(base, y), (base + width - 1, y),
                          (base + width - 1, y + 8)], fill=0)
            draw.polygon([(base, y + height), (base + width - 1, y + height),
                          (base + width - 1, y + height - 8)], fill=0)
        else:
            draw.rectangle((base, y, base + 6, y + height), fill=0)
            draw.polygon([(base, y), (base + width - 1, y), (base, y + 8)], fill=0)
            draw.polygon([(base, y + height), (base + width - 1, y + height),
                          (base, y + height - 8)], fill=0)


def test_open_bracket_at_actual_column_edge_is_not_clipped():
    # Measured printed 三民 open bracket: 25-26px wide, 85-86px high at
    # column.left itself. The old left+0.5*66 crop lost entire openers.
    image = Image.new("L", (850, 780), 255)
    draw = ImageDraw.Draw(image)
    for y in (110, 310, 520):
        _bracket_pair(draw, 56, y, width=26, height=85, span=205)
    found = recover_bracketed_ordinary_entries(
        [], image, [SimpleNamespace(left=58, right=810)],
        30, 740, 66,
    )
    assert len(found) == 3
    assert all(abs(item.y - y) <= 12 for item, y in zip(
        sorted(found, key=lambda entry: entry.y), (110, 310, 520)
    ))


def test_small_unsampled_square_brackets_can_start_a_headword():
    # XDHYCD printable openings measure ~15px x 28px for 17-18px body
    # characters. This is purely image evidence, without sampled 【】.
    image = Image.new("L", (540, 500), 255)
    d = ImageDraw.Draw(image)
    for y in (78, 174, 302):
        _bracket_pair(d, 18, y, width=15, height=28, span=111)
    result = recover_bracketed_ordinary_entries(
        [], image, [SimpleNamespace(left=16, right=510)],
        20, 490, 18,
    )
    assert len(result) == 3


def test_crossing_ink_recovers_previous_whitespace_without_invented_row():
    # Three oversized printed heads: true top separator precedes a
    # dark body by ~1 text line. Raster rows intentionally mimic TDCNTD.
    image = np.full((600, 180), 255, dtype=np.uint8)
    entries = [Entry("", x=28, y=y) for y in (133, 283, 433, 583)]
    for y in (133, 283, 433):
        image[y - 46:y - 33, 28:73] = 20  # previous paragraph
        image[y - 9:y + 29, 28:73] = 20   # current large printed glyph
    # Last entry deliberately has no crossing evidence, as can occur with
    # disconnected individual ideographs; use measured page coherence.
    img = Image.fromarray(image, "L")
    corrected, shift = adjust_page_coherent_crossing_separators(
        entries, img, 25,
    )
    assert 17 <= shift <= 28
    assert all(abs(raw.y - updated.y - shift) <= 0 for raw, updated in zip(entries, corrected))


def test_normal_separators_never_shift_without_ink_before_line():
    image = np.full((500, 180), 255, dtype=np.uint8)
    entries = [Entry("", 28, y) for y in (100, 225, 350)]
    for y in (100, 225, 350):
        image[y + 4:y + 38, 28:72] = 5
    corrected, shift = adjust_page_coherent_crossing_separators(
        entries, Image.fromarray(image, "L"), 25,
    )
    assert shift == 0
    assert [entry.y for entry in corrected] == [100, 225, 350]


class Identity:
    def source_to_canonical_point(self, x, y, _source):
        return x, y

    def canonical_to_source_point(self, x, y, _source):
        return x, y


def _fallback_columns():
    cols = [
        SimpleNamespace(left=30, right=620, lines=[object()] * 45),
        SimpleNamespace(left=700, right=1320, lines=[object()] * 55),
    ]
    layout = SimpleNamespace(
        columns=cols, transform=Identity(), source_size=(1400, 2000),
    )
    understanding = SimpleNamespace(layout=layout)
    prior = [Entry("", 30, 130), Entry("", 30, 550)]
    return understanding, prior


def test_independent_latin_column_requires_repeated_entry_and_body_family(monkeypatch):
    from picture_capture import dictionary_page_design_refined as refined

    understanding, previous = _fallback_columns()
    settings = AppSettings(
        dictionary_profile_id="latin_regular",
        ocr_language="spa",
    )
    raw = [
        SimpleNamespace(
            left=30, lines=[object()] * 50, body_mode=SimpleNamespace(support=40, center=31),
            entry_modes=[],
        ),
        SimpleNamespace(
            left=700, lines=[object()] * 54,
            body_mode=SimpleNamespace(support=27, center=30.0),
            entry_modes=[SimpleNamespace(support=26, center=0.0)],
        ),
    ]
    layout = SimpleNamespace(
        columns=raw, reliable=True, ordinary_line_height=40,
        source_size=(1400, 2000), transform=Identity(),
    )
    independent_entries = [Entry("", 700, 100 + 55 * i) for i in range(26)]
    monkeypatch.setattr(refined, "detect_entries_from_page_design",
                        lambda *_a, **_kw: SimpleNamespace(
                            layout=layout, entries=independent_entries
                        ))
    result = recover_depleted_indent_columns(
        Image.new("L", (1400, 2000), 255),
        settings, understanding, previous,
    )
    assert len(result) == 28
    assert sum(entry.x == 700 for entry in result) == 26
    assert sum(entry.x == 30 for entry in result) == 2

    raw[1].entry_modes = [SimpleNamespace(support=2, center=0.0)]
    assert len(recover_depleted_indent_columns(
        Image.new("L", (1400, 2000), 255), settings, understanding, previous
    )) == 2


def test_cjk_never_uses_latin_independent_fallback():
    understanding, previous = _fallback_columns()
    settings = AppSettings(dictionary_profile_id="cjk_visual", ocr_language="ch")
    assert recover_depleted_indent_columns(
        Image.new("L", (1400, 2000), 255), settings, understanding, previous,
    ) == previous


def test_real_export_logical_section_numbers_cannot_cross_physical_columns():
    """Nôm training-v3 pages label two physical X columns as logical column=0."""
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "audit_ordinary_training_v3.py"
    spec = importlib.util.spec_from_file_location("ordinary_v3_audit", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Same Y and logical column but different actual page-column X: no match.
    left = [{"column": 0, "source_x": 60, "source_y": 120}]
    right = [{"column": 0, "source_x": 569, "source_y": 120}]
    assert module.ordered_alignment(left, right, 12, [60, 569])[0] == 0
    assert module.ordered_alignment(left, left, 12, [60, 569])[0] == 1
