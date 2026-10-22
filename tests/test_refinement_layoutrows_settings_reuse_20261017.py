"""Explicit Y refinement reuses saved page geometry despite unrelated settings edits."""
from dataclasses import replace
from types import SimpleNamespace

from PIL import Image

from picture_capture.geometry.layout_transform import LayoutTransform
from picture_capture.layout_rows_cache import write_layout_rows_cache
from picture_capture.refinement.layoutrows import (
    cached_refinement_settings, refinement_cache_miss_reason,
)
from picture_capture.models import AppSettings


def test_refinement_reads_json_even_when_global_settings_fingerprint_changes(tmp_path):
    page = tmp_path / "070966.png"
    Image.new("RGB", (250, 350), "white").save(page)
    rows = [SimpleNamespace(y0=12+i*25, y1=30+i*25, first_x=3, anchor_x=10)
            for i in range(6)]
    layout = SimpleNamespace(
        transform=LayoutTransform("identity"),
        source_size=(250, 350), canonical_size=(250, 350),
        body_top=12, body_bottom=250, ordinary_line_height=25,
        columns=[SimpleNamespace(index=0, left=11, right=91, lines=rows)],
    )
    saved = AppSettings(columns=1, manual_x=11, column_width=80)
    assert write_layout_rows_cache(tmp_path, page, 3, saved, layout) is not None

    # The explicit button and unrelated UI switch change repr(settings).
    current = replace(saved, paddle_refine_separator_y=True, right_ratio=85.0)
    current.ordinary_auto_layout = True
    current.ordinary_auto_columns = True
    current.ordinary_auto_start_y = True
    current.ordinary_auto_manual_x = True
    current.ordinary_auto_character_height = True
    current.ordinary_auto_column_width = True
    current.ordinary_auto_gutter = False
    current.ordinary_auto_row_padding = False

    hit = cached_refinement_settings(page, (250, 350), current, 3)
    assert hit is not None
    effective, fields = hit
    assert fields == {
        "columns": 1, "start_y": 12, "manual_x": 11,
        "character_height": 25, "column_width": 80,
    }
    assert effective.manual_x == 11
    assert refinement_cache_miss_reason(page, (250, 350), current, 3) != "layoutrows_settings_changed"


def test_refinement_rejects_other_page_json(tmp_path):
    page = tmp_path / "page.png"
    Image.new("RGB", (250, 350), "white").save(page)
    rows = [SimpleNamespace(y0=12+i*25, y1=30+i*25, first_x=3, anchor_x=10)
            for i in range(6)]
    layout = SimpleNamespace(
        transform=LayoutTransform("identity"),
        source_size=(250, 350), canonical_size=(250, 350),
        body_top=12, body_bottom=250, ordinary_line_height=25,
        columns=[SimpleNamespace(index=0, left=11, right=91, lines=rows)],
    )
    cfg = AppSettings()
    assert write_layout_rows_cache(tmp_path, page, 3, cfg, layout) is not None
    assert cached_refinement_settings(page, (250, 350), cfg, 4) is None


def test_cached_batch_restores_four_or_eight_workers(tmp_path):
    from picture_capture.refinement.parallel import configured_refine_workers

    settings = AppSettings(columns=1, manual_x=11, column_width=80)
    settings.ordinary_auto_layout = True
    settings.ordinary_auto_columns = True
    settings.ordinary_auto_start_y = True
    settings.ordinary_auto_manual_x = True
    settings.ordinary_auto_column_width = True
    settings.ordinary_auto_gutter = False
    settings.ordinary_auto_row_padding = False
    settings.ordinary_auto_character_height = True
    settings.layout_mask_illustrations = True
    settings.layout_mask_illustrations_use_existing = True
    pages = []
    rows = [SimpleNamespace(y0=12+i*25, y1=30+i*25, first_x=3, anchor_x=10)
            for i in range(6)]
    layout = SimpleNamespace(
        transform=LayoutTransform("identity"),
        source_size=(250, 350), canonical_size=(250, 350),
        body_top=12, body_bottom=250, ordinary_line_height=25,
        columns=[SimpleNamespace(index=0, left=11, right=91, lines=rows)],
    )
    for index in range(8):
        page = tmp_path / f"{index:06}.png"
        Image.new("RGB", (250, 350), "white").save(page)
        assert write_layout_rows_cache(tmp_path, page, index, settings, layout) is not None
        pages.append((page, index))
    settings.paddle_refine_separator_y = True
    assert configured_refine_workers(
        8, cpus=12, configured="auto", settings=settings,
        cache_pages=tuple(pages),
    ) == 4
    assert configured_refine_workers(
        8, cpus=12, configured="8", settings=settings,
        cache_pages=tuple(pages),
    ) == 8
    # A cache miss must not cause multiple GPU model instances.
    pages[-1][0].unlink()
    assert configured_refine_workers(
        8, cpus=12, configured="8", settings=settings,
        cache_pages=tuple(pages),
    ) == 1
