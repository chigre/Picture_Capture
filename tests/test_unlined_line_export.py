from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

from PIL import Image, ImageDraw

from picture_capture.models import Entry
from picture_capture.unlined_export_filter_settings import (
    BLANK_INK_PERCENT_KEY,
    FILTER_BLANK_KEY,
    FILTER_ENABLED_KEY,
    load_unlined_filter_settings,
    save_unlined_filter_settings,
)
from picture_capture.unlined_line_export import (
    OUTPUT_DIRNAME,
    UnlinedRow,
    _save_unlined_rows,
    is_near_blank_row,
    matched_lined_row_keys,
    row_ink_percent,
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


def _save(source, page, rows, output, *, merge=False, enabled=False, blank=False, threshold=0.8):
    return _save_unlined_rows(
        source,
        page,
        rows,
        output,
        merge_by_page=merge,
        filter_enabled=enabled,
        filter_blank=blank,
        blank_ink_percent=threshold,
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


def test_blank_metric_is_background_relative_and_default_threshold_is_conservative():
    pure_white = Image.new("RGB", (100, 20), "white")
    aged_paper = Image.new("RGB", (100, 20), (222, 218, 205))
    tiny_speck = Image.new("RGB", (100, 20), "white")
    tiny_speck_draw = ImageDraw.Draw(tiny_speck)
    tiny_speck_draw.rectangle((5, 5, 7, 7), fill="black")  # 9/2000 = 0.45%
    text_row = Image.new("RGB", (100, 20), "white")
    text_draw = ImageDraw.Draw(text_row)
    text_draw.rectangle((5, 4, 34, 15), fill="black")  # 360/2000 = 18%

    try:
        assert row_ink_percent(pure_white) == 0.0
        assert row_ink_percent(aged_paper) == 0.0
        assert is_near_blank_row(tiny_speck, 0.8) is True
        assert is_near_blank_row(text_row, 0.8) is False
    finally:
        pure_white.close()
        aged_paper.close()
        tiny_speck.close()
        text_row.close()


def test_unlined_export_without_filter_keeps_blank_diagnostic_rows(tmp_path):
    source = Image.new("RGB", (120, 90), "white")
    draw = ImageDraw.Draw(source)
    draw.rectangle((20, 12, 49, 21), fill="black")
    draw.rectangle((30, 62, 69, 71), fill="black")
    rows = [
        UnlinedRow(0, 0, "body", (0, 0, 100, 30), 0),
        # Blank is meaningful for this diagnostic exporter and must survive.
        UnlinedRow(0, 1, "body", (0, 30, 100, 55), 0),
        UnlinedRow(0, 2, "entry", (0, 55, 100, 85), 0),
    ]
    output = tmp_path / OUTPUT_DIRNAME
    page = tmp_path / "page001.jpg"

    exported, blank_rows, filtered_out, merged = _save(source, page, rows, output)
    source.close()

    assert exported == 3
    assert blank_rows == 1
    assert filtered_out == 0
    assert merged is False
    first = output / "page001_UL_000.png"
    blank = output / "page001_UL_001.png"
    third = output / "page001_UL_002.png"
    assert first.is_file() and blank.is_file() and third.is_file()
    with Image.open(first) as image:
        assert image.size == (30, 10)
    # All-white diagnostic keeps the original row frame instead of disappearing.
    with Image.open(blank) as image:
        assert image.size == (100, 25)
    with Image.open(third) as image:
        assert image.size == (40, 10)


def test_blank_filter_exports_only_near_blank_and_preserves_original_row_frame(tmp_path):
    source = Image.new("RGB", (100, 50), "white")
    draw = ImageDraw.Draw(source)
    # Row 0: 3x3 speck => 9 / 2000 = 0.45%, retained by 0.8% filter.
    draw.rectangle((5, 5, 7, 7), fill="black")
    # Row 1: obvious text-like block => far above 0.8%, filtered out.
    draw.rectangle((10, 28, 39, 42), fill="black")
    rows = [
        UnlinedRow(0, 0, "body", (0, 0, 100, 20), 0),
        UnlinedRow(0, 1, "body", (0, 25, 100, 50), 0),
    ]
    output = tmp_path / OUTPUT_DIRNAME
    page = tmp_path / "page_blank_filter.jpg"

    exported, blank_rows, filtered_out, merged = _save(
        source,
        page,
        rows,
        output,
        enabled=True,
        blank=True,
        threshold=0.8,
    )
    source.close()

    assert exported == 1
    assert blank_rows == 1
    assert filtered_out == 1
    assert merged is False
    target = output / "page_blank_filter_UL_000.png"
    assert target.is_file()
    # Critical: blank-filter output is not content-tight cropped to the 3x3 speck.
    with Image.open(target) as image:
        assert image.size == (100, 20)


def test_blank_filter_keeps_fully_white_slice(tmp_path):
    source = Image.new("RGB", (80, 20), "white")
    rows = [UnlinedRow(0, 0, "body", (0, 0, 80, 20), 0)]
    output = tmp_path / OUTPUT_DIRNAME
    page = tmp_path / "page_white.jpg"

    exported, blank_rows, filtered_out, merged = _save(
        source,
        page,
        rows,
        output,
        enabled=True,
        blank=True,
        threshold=0.8,
    )
    source.close()

    assert (exported, blank_rows, filtered_out, merged) == (1, 1, 0, False)
    with Image.open(output / "page_white_UL_000.png") as image:
        assert image.size == (80, 20)


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

    exported, blank_rows, filtered_out, merged = _save(
        source, page, rows, output, merge=True
    )
    source.close()

    assert exported == 1
    assert blank_rows == 0
    assert filtered_out == 0
    assert merged is True
    target = output / "page002_UL_PAGE.png"
    assert target.is_file()
    with Image.open(target) as image:
        assert image.size == (30, 20)
    assert (output / "page002.UnlinedLines").read_text(encoding="utf-8") == (
        "page002_UL_PAGE.png\n"
    )


def test_unlined_filter_settings_share_crop_store_and_preserve_existing_keys(tmp_path):
    root = tmp_path / "project"
    path = root / "QT" / "_CropSettings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"parallel_workers": 4, "entry_left_padding": 9}), encoding="utf-8")

    assert load_unlined_filter_settings(root) == (False, False, 0.8)
    save_unlined_filter_settings(root, enabled=True, blank=True, blank_ink_percent=1.2)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["parallel_workers"] == 4
    assert payload["entry_left_padding"] == 9
    assert payload[FILTER_ENABLED_KEY] is True
    assert payload[FILTER_BLANK_KEY] is True
    assert payload[BLANK_INK_PERCENT_KEY] == 1.2
    assert load_unlined_filter_settings(root) == (True, True, 1.2)


def test_unlined_ui_is_installed_after_single_line_button_and_reuses_parallel_crop_setting():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "src" / "picture_capture" / "launcher.py").read_text(encoding="utf-8")
    ui = (root / "src" / "picture_capture" / "unlined_line_export_ui.py").read_text(encoding="utf-8")
    exporter = (root / "src" / "picture_capture" / "unlined_line_export.py").read_text(encoding="utf-8")
    filters = (root / "src" / "picture_capture" / "unlined_export_filter_settings.py").read_text(encoding="utf-8")

    assert 'install_postproduction_single_line_runtime(app_module)' in launcher
    assert 'install_unlined_line_export_ui(app_module)' in launcher
    assert 'install_unlined_export_filter_settings_ui(app_module)' in launcher
    assert launcher.index('install_postproduction_single_line_runtime(app_module)') < launcher.index(
        'install_unlined_line_export_ui(app_module)'
    )
    assert '_BUTTON_TEXT = "未画线行导出"' in ui
    assert '_LEFT_NEIGHBOR_TEXT = "单行切图"' in ui
    assert '"after": target' in ui
    assert 'OUTPUT_DIRNAME = "PSW_UNLINED"' in exporter
    assert 'configured_single_line_workers(project_root)' in exporter
    assert 'get_context("spawn")' in exporter
    # Critical semantic locks: export is Layout-minus-PDIC, and blankness is
    # measured on the original row crop before white-border trimming.
    assert 'role == "body"' not in exporter
    assert 'matched_lined_row_keys(layout, entries)' in exporter
    assert exporter.index('ink_percent = row_ink_percent(crop)') < exporter.index(
        'trimmed = _trim_white_border(crop)'
    )
    assert 'FILTER_LABEL = "未画线行导出过滤"' in filters
    assert 'BLANK_LABEL = "空白"' in filters
    assert 'DEFAULT_BLANK_INK_PERCENT = 0.8' in filters
