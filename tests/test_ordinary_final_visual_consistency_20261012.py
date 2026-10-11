"""Test actual final candidate suppression, not only raw LayoutLine roles.

Real XDHYCD page 0009 showed 60 identical emitted separators despite the
previous raw-row correction. These fixtures model the *output marker Y* and
actual printed ink around it, keeping the user scan outside Git history.
"""
from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_final_visual_consistency import (
    correct_anomalous_final_ordinary_entries,
)


def _settings():
    return AppSettings(
        dictionary_profile_id="cjk_visual",
        ocr_language="chi_sim",
        profile_parser_controls_version=2,
        profile_cjk_brackets_in_body=True,
    )


def _page(*, false_per_column=9, with_heads=False):
    image = Image.new("RGB", (900, 1750), "white")
    draw = ImageDraw.Draw(image)
    cols = []
    entries = []
    for index, left in enumerate((40, 460)):
        lines = [
            SimpleNamespace(role="entry", y0=100 + 50 * i, y1=129 + 50 * i)
            for i in range(22)
        ]
        # Distinct stable body and entry lanes, as observed in page 0009.
        column = SimpleNamespace(
            index=index, left=left, right=left+380, lines=lines,
            body_mode=SimpleNamespace(center=38.0, support=19),
            entry_modes=[SimpleNamespace(center=1.0, support=22)],
        )
        cols.append(column)
        for i in range(22):
            y = 100 + 50 * i
            x = left + (34 if i < false_per_column else 1)
            draw.rectangle((x, y+1, x+70, y+26), fill="black")
            entries.append(Entry(
                word="", x=left, y=y,
                ocr_source="page_understanding:ordinary_layout_role",
            ))
        # Never suppress visual pair evidence, even at a body-indented X.
        draw.rectangle((left+45, 1200, left+92, 1228), fill="black")
        entries.append(Entry(
            word="", x=left, y=1200,
            ocr_source="ordinary_bracket_pair",
        ))
        if with_heads:
            for y in (1250, 1450, 1600):
                draw.rectangle((left+1, y, left+70, y+71), fill="black")
                entries.append(Entry(
                    word="", x=left, y=y+38,
                    ocr_source="page_understanding:ordinary_layout_role",
                ))
    layout = SimpleNamespace(
        transform=SimpleNamespace(kind="identity"),
        indent_type="body", ordinary_line_height=29.0,
        body_top=50, body_bottom=image.height,
        columns=cols,
    )
    return image, _settings(), layout, entries


def test_two_columns_with_repeated_contradictions_remove_final_marker_candidates():
    image, settings, layout, old = _page()
    result, stats = correct_anomalous_final_ordinary_entries(
        image, settings, layout, old,
    )
    assert stats["repaired_columns"] == [0, 1]
    assert stats["removed_false_entries"] == 18
    assert len(result) == len(old) - 18
    assert sum(e.ocr_source == "ordinary_bracket_pair" for e in result) == 2


def test_isolated_ambiguity_does_not_change_normal_pages():
    image, settings, layout, old = _page(false_per_column=1)
    result, stats = correct_anomalous_final_ordinary_entries(
        image, settings, layout, old,
    )
    assert not stats["repaired_columns"]
    assert len(result) == len(old)
    assert [(e.x, e.y) for e in result] == [(e.x, e.y) for e in old]


def test_restores_tall_head_tops_and_discards_internal_duplicate_candidates():
    image, settings, layout, old = _page(with_heads=True)
    result, stats = correct_anomalous_final_ordinary_entries(
        image, settings, layout, old,
    )
    assert stats["repaired_columns"] == [0, 1]
    assert stats["removed_false_entries"] >= 18
    assert stats["removed_glyph_fragments"] >= 4
    assert stats["added_verified_heads"] >= 4
    for x in (40, 460):
        for y in (1120, 1330, 1430):
            assert any(e.x == x and abs(e.y-y) <= 7 for e in result)


def test_non_cjk_or_wrong_indent_does_not_intervene():
    image, settings, layout, old = _page()
    layout.indent_type = "headword"
    result, stats = correct_anomalous_final_ordinary_entries(
        image, settings, layout, old,
    )
    assert len(result) == len(old) and not stats["repaired_columns"]
    layout.indent_type = "body"
    settings.ocr_language = "eng"
    settings.dictionary_profile_id = "latin_regular"
    settings.paddle_language = "en"
    result, stats = correct_anomalous_final_ordinary_entries(
        image, settings, layout, old,
    )
    assert len(result) == len(old) and not stats["repaired_columns"]
