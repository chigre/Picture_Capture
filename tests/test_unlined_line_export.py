from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture.models import Entry
from picture_capture.unlined_line_export import (
    OUTPUT_DIRNAME,
    UnlinedRow,
    _save_trimmed_unlined_rows,
    matched_lined_row_keys,
    unlined_rows_from_layout,
)


class _IdentityTransform:
    def source_to_canonical_point(self, x, y, source_size):
        return int(x), int(y)

    def canonical_to_source_point(self, x, y, source_size):
        return int(x), int(y)


def _line(y0: int, y1: int, role: str):
    return SimpleNamespace(y0=y0, y1=y1, role=role)


def _layout():
    lines = [
        _line(10, 25, "entry"),
        _line(40, 55, "body"),
        # Deliberately role=entry with no PDIC marker. "Unlined" must be based
        # on visible/current marker state, not semantic role.
        _line(70, 85, "entry"),
    ]
    column = SimpleNamespace(index=0, left=10, right=140, lines=lines)
    return SimpleNamespace(
        transform=_IdentityTransform(),
        source_size=(200, 200),
        body_top=20,
        body_bottom=180,
        ordinary_line_height=20.0,
        columns=[column],
    )


def test_unlined_rows_are_layout_minus_actual_pdic_markers_not_body_roles():
    layout = _layout()
    # First row boundary: y0=10 and no previous line => 10 - 0.35*20 = 3;
    # add body_top=20 => source marker Y=23.
    entries = [Entry(word="A", x=10, y=23)]

    assert matched_lined_row_keys(layout, entries) == {(0, 0)}
    rows, layout_rows, lined_rows = unlined_rows_from_layout(layout, entries, None)

    assert layout_rows == 3
    assert lined_rows == 1
    assert [(row.column_index, row.line_index) for row in rows] == [(0, 1), (0, 2)]
    assert [row.role for row in rows] == ["body", "entry"]


def test_unlined_export_trims_each_slice_and_discards_blank_rows(tmp_path):
    source = Image.new("RGB", (120, 90), "white")
    draw = ImageDraw.Draw(source)
    draw.rectangle((20, 12, 49, 21), fill="black")
    draw.rectangle((30, 62, 69, 71), fill="black")
    rows = [
        UnlinedRow(0, 0, "body", (0, 0, 100, 30), 0),
        # Entirely white middle slice must disappear.
        UnlinedRow(0, 1, "body", (0, 30, 100, 55), 0),
        UnlinedRow(0, 2, "entry", (0, 55, 100, 85), 0),
    ]
    output = tmp_path / OUTPUT_DIRNAME
    page = tmp_path / "page001.jpg"

    exported, blank_rows, merged = _save_trimmed_unlined_rows(
        source, page, rows, output, merge_by_page=False
    )
    source.close()

    assert exported == 2
    assert blank_rows == 1
    assert merged is False
    first = output / "page001_UL_000.png"
    second = output / "page001_UL_001.png"
    assert first.is_file() and second.is_file()
    with Image.open(first) as image:
        assert image.size == (30, 10)
    with Image.open(second) as image:
        assert image.size == (40, 10)
    assert (output / "page001.UnlinedLines").read_text(encoding="utf-8") == (
        "page001_UL_000.png\npage001_UL_001.png\n"
    )


def test_unlined_export_can_merge_trimmed_rows_per_page(tmp_path):
    source = Image.new("RGB", (100, 70), "white")
    draw = ImageDraw.Draw(source)
    draw.rectangle((10, 5, 29, 14), fill="black")
    draw.rectangle((10, 45, 39, 54), fill="black")
    rows = [
        UnlinedRow(0, 0, "body", (0, 0, 80, 25), 0),
        UnlinedRow(0, 1, "body", (0, 35, 80, 65), 0),
    ]
    output = tmp_path / OUTPUT_DIRNAME
    page = tmp_path / "page002.jpg"

    exported, blank_rows, merged = _save_trimmed_unlined_rows(
        source, page, rows, output, merge_by_page=True
    )
    source.close()

    assert exported == 1
    assert blank_rows == 0
    assert merged is True
    target = output / "page002_UL_PAGE.png"
    assert target.is_file()
    with Image.open(target) as image:
        assert image.size == (30, 20)
    assert (output / "page002.UnlinedLines").read_text(encoding="utf-8") == (
        "page002_UL_PAGE.png\n"
    )


def test_unlined_ui_is_installed_after_single_line_button_and_reuses_parallel_crop_setting():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "src" / "picture_capture" / "launcher.py").read_text(encoding="utf-8")
    ui = (root / "src" / "picture_capture" / "unlined_line_export_ui.py").read_text(encoding="utf-8")
    exporter = (root / "src" / "picture_capture" / "unlined_line_export.py").read_text(encoding="utf-8")

    assert 'install_postproduction_single_line_runtime(app_module)' in launcher
    assert 'install_unlined_line_export_ui(app_module)' in launcher
    assert launcher.index('install_postproduction_single_line_runtime(app_module)') < launcher.index(
        'install_unlined_line_export_ui(app_module)'
    )
    assert '_BUTTON_TEXT = "未画线行导出"' in ui
    assert '_LEFT_NEIGHBOR_TEXT = "单行切图"' in ui
    assert '"after": target' in ui
    assert 'OUTPUT_DIRNAME = "PSW_UNLINED"' in exporter
    assert 'configured_single_line_workers(project_root)' in exporter
    assert 'get_context("spawn")' in exporter
    # Critical semantic lock: export is not implemented as role == body.
    assert 'role == "body"' not in exporter
    assert 'matched_lined_row_keys(layout, entries)' in exporter
