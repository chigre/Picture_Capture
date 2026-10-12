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
    suppress_blank_layout_rows_before_proven_head,
    suppress_proven_bracket_body_continuations,
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
        for y in (1250, 1450, 1600):
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


def test_empty_role_marker_immediately_before_proven_head_is_rejected():
    """Reproduce two stray XDHYCD pinyin-continuation boundaries.

    Reject only a *blank* Layout-role marker when the following accepted
    entry is independently verified as a large printed head.
    """
    image, settings, layout, _entries = _page(false_per_column=0)
    draw = ImageDraw.Draw(image)
    existing = [
        Entry("", 40, 1060, ocr_source="ordinary_verified_final_large_head"),
        Entry("", 460, 960, ocr_source="ordinary_bracket_pair"),
    ]
    blank = [
        Entry("", 40, 1018, ocr_source="page_understanding:ordinary_layout_role"),
        Entry("", 460, 918, ocr_source="page_understanding:ordinary_layout_role"),
    ]
    # The test fixture has regular ink at y=100+50*i. Keep the no-ink
    # spans by placing extra independent test glyphs far below them.
    image = Image.new("L", (900, 1050), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 960, 95, 987), fill=0)
    draw.rectangle((460, 960, 510, 987), fill=0)
    examples = [
        Entry("", 40, 918, ocr_source="page_understanding:ordinary_layout_role"),
        Entry("", 40, 960, ocr_source="ordinary_verified_final_large_head"),
        Entry("", 460, 918, ocr_source="page_understanding:ordinary_layout_role"),
        Entry("", 460, 960, ocr_source="ordinary_bracket_pair"),
    ]
    filtered, count = suppress_blank_layout_rows_before_proven_head(
        image, settings, layout, examples,
    )
    assert count == 2
    assert len(filtered) == 2
    assert {e.ocr_source for e in filtered} == {
        "ordinary_verified_final_large_head", "ordinary_bracket_pair",
    }


def test_blank_marker_is_not_rejected_without_a_proven_next_head():
    image, settings, layout, _entries = _page(false_per_column=0)
    markers = [
        Entry("", 40, 1180, ocr_source="page_understanding:ordinary_layout_role"),
        Entry("", 40, 1222, ocr_source="page_understanding:ordinary_layout_role"),
    ]
    filtered, count = suppress_blank_layout_rows_before_proven_head(
        image, settings, layout, markers,
    )
    assert count == 0 and len(filtered) == 2


def test_visible_deep_indented_text_is_never_rejected_as_empty():
    image, settings, layout, _entries = _page(false_per_column=0)
    draw = ImageDraw.Draw(image)
    draw.rectangle((40+185, 1180, 40+220, 1200), fill=0)
    markers = [
        Entry("", 40, 1180, ocr_source="page_understanding:ordinary_layout_role"),
        Entry("", 40, 1222, ocr_source="ordinary_verified_final_large_head"),
    ]
    filtered, count = suppress_blank_layout_rows_before_proven_head(
        image, settings, layout, markers,
    )
    assert count == 0 and len(filtered) == 2


def test_adjacent_proven_bracket_body_continuations_are_not_new_entries():
    """An intact bracket word may be followed one pitch later by inset body."""
    image, settings, layout, _baseline = _page(false_per_column=0)
    image = Image.new("L", (900, 1000), 255)
    paint = ImageDraw.Draw(image)
    entries = []
    for left in (40, 460):
        for head_y in (180, 640):
            # Printed bracket/entry in the outer lane.
            paint.rectangle((left+4, head_y, left+80, head_y+25), fill=0)
            # A continuation 41/43 px later starts in the measured body lane.
            body_y = head_y + (41 if head_y == 180 else 43)
            paint.rectangle((left+45, body_y+1, left+140, body_y+25), fill=0)
            entries.extend([
                Entry("", left, head_y, ocr_source="ordinary_bracket_pair"),
                Entry("", left, body_y,
                      ocr_source="page_understanding:ordinary_layout_role"),
            ])
    result, removed = suppress_proven_bracket_body_continuations(
        image, settings, layout, entries,
    )
    assert len(result) == 4
    assert len(removed) == 4
    assert {row["first_ink_offset"] for row in removed} == {45.0}
    assert all(item.ocr_source == "ordinary_bracket_pair" for item in result)


def test_bracket_continuation_guard_never_vetoes_next_proven_lemma():
    image, settings, layout, _entries = _page(false_per_column=0)
    image = Image.new("L", (900, 600), 255)
    paint = ImageDraw.Draw(image)
    # A genuine tightly spaced next word begins in the outer entry lane.
    paint.rectangle((44, 241, 130, 267), fill=0)
    # A second independently bracket-confirmed entry is never demoted.
    paint.rectangle((505, 241, 585, 267), fill=0)
    entries = [
        Entry("", 40, 200, ocr_source="ordinary_bracket_pair"),
        Entry("", 40, 240, ocr_source="page_understanding:ordinary_layout_role"),
        Entry("", 460, 200, ocr_source="ordinary_bracket_pair"),
        Entry("", 460, 240, ocr_source="ordinary_bracket_pair"),
    ]
    actual, removed = suppress_proven_bracket_body_continuations(
        image, settings, layout, entries,
    )
    assert len(actual) == 4 and not removed


def test_bracket_continuation_guard_respects_oversized_and_weak_layouts():
    image, settings, layout, _entries = _page(false_per_column=0)
    image = Image.new("L", (900, 600), 255)
    ImageDraw.Draw(image).rectangle((85, 241, 154, 266), fill=0)
    existing = [
        Entry("", 40, 200, ocr_source="ordinary_bracket_pair"),
        Entry("", 40, 240, ocr_source="page_understanding:ordinary_layout_role",
              ocr_oversized_cjk=True),
    ]
    unchanged, events = suppress_proven_bracket_body_continuations(
        image, settings, layout, existing,
    )
    assert len(unchanged) == 2 and events == []
    existing[1].ocr_oversized_cjk = False
    layout.columns[0].body_mode.support = 1
    unchanged, events = suppress_proven_bracket_body_continuations(
        image, settings, layout, existing,
    )
    assert len(unchanged) == 2 and events == []
