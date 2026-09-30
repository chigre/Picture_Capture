from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from picture_capture.dictionary_page_design import (
    ColumnDesign,
    DictionaryPageLayout,
    IndentMode,
    LayoutLine,
    PageRegion,
    PageRegions,
)
from picture_capture.dictionary_page_design_refined import refine_indent_semantics
from picture_capture.layout_transform import LayoutTransform
from picture_capture.models import Entry
from picture_capture.training_baseline import (
    baseline_path_for_pdic,
    build_write_pdic_capture,
)
from picture_capture.training_export_v3 import (
    compare_automatic_and_final,
    select_page_range,
)


def _line(x: int, y: int, patch: np.ndarray) -> LayoutLine:
    return LayoutLine(
        column=0,
        y0=y,
        y1=y + 56,
        first_x=x,
        anchor_x=x,
        anchor_width=50,
        anchor_height=54,
        gap_before=20,
        patch=patch,
    )


def test_refinement_keeps_intermediate_indent_as_layout_not_entry():
    reference = 60.0
    body_lines = [
        _line(20, 80 + index * 80, np.zeros((12, 12), dtype=bool))
        for index in range(8)
    ]
    # A repeated quotation/continuation indent around 0.5h. Empty patches make
    # clear that position alone must not turn it into an entry family.
    middle_lines = [
        _line(50, 1200 + index * 80, np.zeros((12, 12), dtype=bool))
        for index in range(4)
    ]
    # True headword indent is a deeper family with a stable leading structure.
    entry_patch = np.zeros((12, 12), dtype=bool)
    entry_patch[:, :3] = True
    entry_lines = [
        _line(140, 1800 + index * 160, entry_patch.copy())
        for index in range(4)
    ]
    body = IndentMode(center=20.0, tolerance=8.0, lines=body_lines, role="body")
    middle = IndentMode(center=50.0, tolerance=8.0, lines=middle_lines)
    true_entry = IndentMode(center=140.0, tolerance=8.0, lines=entry_lines)
    column = ColumnDesign(
        index=0,
        left=40,
        right=800,
        gutter_after=40,
        lines=body_lines + middle_lines + entry_lines,
        indent_modes=[body, middle, true_entry],
        body_mode=body,
        # Simulate the permissive base classifier before refinement.
        entry_modes=[middle, true_entry],
    )
    region = PageRegion("body", (0, 0, 1000, 3000), (0, 0, 1000, 3000), "inferred")
    layout = DictionaryPageLayout(
        transform=LayoutTransform("identity"),
        source_size=(1000, 3000),
        canonical_size=(1000, 3000),
        regions=PageRegions(body=region),
        body_top=0,
        body_bottom=3000,
        columns=[column],
        ordinary_line_height=reference,
        ordinary_line_pitch=80.0,
        ordinary_char_width=56.0,
        ordinary_char_height=reference,
        indent_type="headword",
        reliable=True,
    )

    family = refine_indent_semantics(layout)

    assert family is not None
    assert family.offset_ratio > 1.5
    assert middle.role == "other_indent"
    assert true_entry.role == "entry"
    assert all(middle is not mode for mode in column.entry_modes)
    assert any(true_entry is mode for mode in column.entry_modes)


def test_training_diff_reports_added_deleted_moved_and_unchanged():
    automatic = [
        {"source_x": 50, "source_y": 100, "column": 0},
        {"source_x": 50, "source_y": 300, "column": 0},
        {"source_x": 1600, "source_y": 500, "column": 1},
    ]
    final = [
        {"source_x": 45, "source_y": 101, "column": 0},
        {"source_x": 45, "source_y": 325, "column": 0},
        {"source_x": 1608, "source_y": 900, "column": 1},
    ]

    diff = compare_automatic_and_final(automatic, final, line_height=60)

    assert diff["summary"] == {
        "automatic_count": 3,
        "final_count": 3,
        "unchanged_count": 1,
        "moved_count": 1,
        "added_count": 1,
        "deleted_count": 1,
    }
    assert diff["moved"][0]["source_y_delta"] == 25


def test_automatic_pdic_snapshot_survives_later_manual_save(tmp_path: Path):
    writes: list[list[Entry]] = []

    def original(_path: Path, entries: list[Entry], _width: int, _pages):
        writes.append(list(entries))

    writer = build_write_pdic_capture(original)
    pdic = tmp_path / "020093.pdic"
    automatic = [
        Entry(
            word="",
            x=57,
            y=133,
            confidence=0.96,
            ocr_source="ordinary_page_design",
            issue_type="ORDINARY_PAGE_DESIGN_ENTRY",
        )
    ]
    writer(pdic, automatic, 3200, ("020093.png", "@", "@"))
    snapshot = baseline_path_for_pdic(pdic)
    assert snapshot.exists()
    first = json.loads(snapshot.read_text(encoding="utf-8"))
    assert first["entries"][0]["source_y"] == 133

    # PDIC-loaded/manual entries carry no runtime detector evidence; this save
    # must not replace the historical automatic baseline.
    writer(pdic, [Entry(word="", x=45, y=160)], 3200, ("020093.png", "@", "@"))
    second = json.loads(snapshot.read_text(encoding="utf-8"))
    assert second == first
    assert len(writes) == 2


def test_training_page_range_is_inclusive_and_accepts_numeric_ids():
    pages = [Path(f"{number:06d}.png") for number in range(89, 100)]
    selected = select_page_range(pages, "92", "000096")
    assert [page.stem for page in selected] == [
        "000092", "000093", "000094", "000095", "000096"
    ]
