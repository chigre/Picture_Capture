from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

from PIL import Image, ImageDraw

from picture_capture.models import Entry
from picture_capture.unlined_export_filter_settings import (
    LEFT_WHITE_PERCENT_KEY,
    DEFAULT_LEFT_WHITE_PERCENT,
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
    left_contiguous_white_percent,
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


def _save(source, page, rows, output, *, merge=False, enabled=False, blank=False, threshold=50.0):
    return _save_unlined_rows(
        source,
        page,
        rows,
        output,
        merge_by_page=merge,
        filter_enabled=enabled,
        filter_blank=blank,
        left_white_percent=threshold,
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
    assert not list(output.glob("*.PSWords"))
    assert not (output / "page001.UnlinedLines").exists()
    with Image.open(first) as image:
        assert image.size == (30, 10)
    # All-white diagnostic keeps the original row frame instead of disappearing.
    with Image.open(blank) as image:
        assert image.size == (100, 25)
    with Image.open(third) as image:
        assert image.size == (40, 10)


def test_white_run_filter_preserves_original_row_frame(tmp_path):
    source = Image.new("RGB", (100, 50), "white")
    draw = ImageDraw.Draw(source)
    # Row 0: substantial ink on the right, but 70% contiguous white on left.
    draw.rectangle((70, 4, 94, 18), fill="black")
    # Row 1: ink starts at 10%, so the left-side run is too short.
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
        threshold=50.0,
    )
    source.close()

    assert exported == 1
    assert blank_rows == 1
    assert filtered_out == 1
    assert merged is False
    target = output / "page_blank_filter_UL_000.png"
    assert target.is_file()
    # Critical: retained prefix must include the original 70% white left side.
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
        threshold=50.0,
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
    assert not (output / "page002.UnlinedLines").exists()


def test_unlined_filter_settings_share_crop_store_and_preserve_existing_keys(tmp_path):
    root = tmp_path / "project"
    path = root / "QT" / "_CropSettings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"parallel_workers": 4, "entry_left_padding": 9}), encoding="utf-8")

    assert load_unlined_filter_settings(root) == (False, False, 50.0)
    save_unlined_filter_settings(root, enabled=True, blank=True, left_white_percent=62.5)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["parallel_workers"] == 4
    assert payload["entry_left_padding"] == 9
    assert payload[FILTER_ENABLED_KEY] is True
    assert payload[FILTER_BLANK_KEY] is True
    assert payload[LEFT_WHITE_PERCENT_KEY] == 62.5
    assert load_unlined_filter_settings(root) == (True, True, 62.5)


def test_unlined_ui_is_explicit_and_reuses_parallel_crop_setting():
    root = Path(__file__).resolve().parents[1]
    composition = (
        root / "src" / "picture_capture" / "bootstrap" / "gui.py"
    ).read_text(encoding="utf-8")
    controller = (
        root / "src" / "picture_capture" / "ui" / "controllers" / "crop.py"
    ).read_text(encoding="utf-8")
    app_source = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    exporter = (root / "src" / "picture_capture" / "unlined_line_export.py").read_text(encoding="utf-8")
    filters = (root / "src" / "picture_capture" / "unlined_export_filter_settings.py").read_text(encoding="utf-8")
    crop_ui = (
        root / "src" / "picture_capture" / "ui" / "settings" / "crop.py"
    ).read_text(encoding="utf-8")
    crop_schema = (
        root / "src" / "picture_capture" / "crop" / "settings.py"
    ).read_text(encoding="utf-8")

    assert "install_unlined_line_export_ui" not in composition
    assert "unlined_line_export_ui" not in composition
    assert "install_unlined_export_filter_settings_ui(app_module)" not in composition
    assert "install_unlined_fast_path" not in composition
    assert "unlined_fast_path_runtime" not in composition
    tasks = (root / "src/picture_capture/ui/compact_task_menus.py").read_text(encoding="utf-8")
    for action in ("split_single_lines_selected_scope", "export_unlined_rows_selected_scope",
                   "split_entries_selected_scope", "split_illustrations_selected_scope"):
        assert action in tasks
    assert "app._pc_single_line_crop_button = button" in tasks
    assert "app._pc_unlined_export_button = button" in tasks
    assert "def export_unlined_rows_selected_scope(self)" in app_source
    assert "def export_unlined_rows_selected_scope(self)" in controller
    assert "app._start_parallel_batch_task(" in controller
    assert "unlined_export.export_unlined_page_job" in controller
    assert 'OUTPUT_DIRNAME = "PSW_UNLINED"' in exporter
    assert "resolve_unlined_physical_rows" in exporter
    # Critical semantic locks: export is Layout-minus-PDIC, and the left-white
    # width is measured on the original prefix before white-border trimming.
    assert 'role == "body"' not in exporter
    assert 'matched_lined_row_keys(layout, entries)' in exporter
    assert exporter.index('left_white = left_contiguous_white_percent(crop)') < exporter.index(
        'trimmed = _trim_white_border(crop)'
    )
    assert 'FILTER_LABEL = "未画线行导出过滤"' in filters
    assert 'BLANK_LABEL = "空白"' in filters
    assert DEFAULT_LEFT_WHITE_PERCENT == 50.0
    assert "dialog.__init__ =" not in filters
    assert "setattr(dialog" not in filters
    assert "UNLINED_FILTER_ENABLED_KEY" in crop_schema
    assert "UNLINED_FILTER_BLANK_KEY" in crop_schema
    assert "UNLINED_LEFT_WHITE_PERCENT_KEY" in crop_schema
    assert "save_unlined_filter_settings(" in crop_ui
    assert "filter_threshold_spin" in crop_ui


def test_png_only_unlined_export_removes_stale_lists_for_content_and_empty_pages(tmp_path):
    output = tmp_path / "PSW_UNLINED"
    output.mkdir()
    source = Image.new("RGB", (80, 30), "white")
    ImageDraw.Draw(source).rectangle((5, 5, 25, 16), fill="black")

    page = tmp_path / "page.jpg"
    old_list = output / "page.UnlinedLines"
    old_list.write_text("obsolete output list\n", encoding="utf-8")
    rows = [UnlinedRow(0, 0, "body", (0, 0, 50, 20), 0)]
    exported, *_ = _save(source, page, rows, output)
    assert exported == 1
    assert (output / "page_UL_000.png").exists()
    assert not old_list.exists()

    old_list.write_text("obsolete output list\n", encoding="utf-8")
    exported, *_ = _save(source, page, [], output)
    assert exported == 0
    assert not old_list.exists()
    assert not (output / "page_UL_000.png").exists()

    old_list.write_text("obsolete output list\n", encoding="utf-8")
    exported, *_ = _save(source, page, rows, output, merge=True)
    assert exported == 1
    assert (output / "page_UL_PAGE.png").exists()
    assert not old_list.exists()
    source.close()
