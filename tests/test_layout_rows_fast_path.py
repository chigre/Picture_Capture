from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import inspect

from PIL import Image, ImageDraw

from picture_capture.layout_rows_cache import (
    CACHE_DIRNAME,
    load_layout_rows_cache,
    recover_physical_rows_fast,
    write_layout_rows_cache,
)
from picture_capture.layout_transform import LayoutTransform
from picture_capture.models import AppSettings
from picture_capture.project_storage import ensure_project_storage


def _physical_layout(size=(200, 200)):
    lines = [
        SimpleNamespace(y0=10 + index * 20, y1=20 + index * 20, first_x=3, anchor_x=5, role="entry")
        for index in range(6)
    ]
    column = SimpleNamespace(index=0, left=10, right=160, lines=lines)
    return SimpleNamespace(
        transform=LayoutTransform("identity"),
        source_size=size,
        canonical_size=size,
        body_top=5,
        body_bottom=150,
        ordinary_line_height=10.0,
        columns=[column],
        reliable=True,
    )


def test_layout_rows_cache_lives_under_managed_data_and_is_semantic_free(tmp_path):
    ensure_project_storage(tmp_path, "test")
    page = tmp_path / "000001.png"
    Image.new("RGB", (200, 200), "white").save(page)
    settings = AppSettings(columns=1, manual_x=10, column_width=150, start_y=5, character_height=10)

    path = write_layout_rows_cache(tmp_path, page, 0, settings, _physical_layout())
    assert path is not None
    assert path.parent.name == CACHE_DIRNAME
    assert path.parent.parent.name == "data"

    loaded = load_layout_rows_cache(
        tmp_path,
        page,
        0,
        settings,
        source_size=(200, 200),
    )
    assert loaded is not None
    assert len(loaded.columns) == 1
    assert len(loaded.columns[0].lines) == 6
    # Entry/body is deliberately not persisted: QA owns only physical rows.
    assert {line.role for line in loaded.columns[0].lines} == {"unknown"}
    assert loaded.columns[0].lines[0].y0 == 10
    assert loaded.columns[0].lines[0].y1 == 20


def test_layout_rows_cache_invalidates_when_project_geometry_changes(tmp_path):
    ensure_project_storage(tmp_path, "test")
    page = tmp_path / "000002.png"
    Image.new("RGB", (200, 200), "white").save(page)
    settings = AppSettings(columns=1, manual_x=10, column_width=150, start_y=5, character_height=10)
    assert write_layout_rows_cache(tmp_path, page, 1, settings, _physical_layout()) is not None

    changed = AppSettings(columns=1, manual_x=30, column_width=150, start_y=5, character_height=10)
    assert load_layout_rows_cache(
        tmp_path,
        page,
        1,
        changed,
        source_size=(200, 200),
    ) is None


def test_fast_physical_recovery_finds_rows_without_full_layout_semantics():
    image = Image.new("RGB", (300, 300), "white")
    draw = ImageDraw.Draw(image)
    for index in range(8):
        top = 20 + index * 30
        draw.rectangle((20, top, 170, top + 13), fill="black")

    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=220,
        gutter=0,
        start_y=10,
        character_height=14,
        ordinary_auto_layout=True,
    )
    layout = recover_physical_rows_fast(image, settings, page_index=0)
    image.close()

    assert layout is not None
    assert "fast_physical_rows" in layout.reason
    assert len(layout.columns) == 1
    assert len(layout.columns[0].lines) >= 6


def test_fast_recovery_source_cannot_call_full_layout_or_semantic_evidence():
    source = inspect.getsource(recover_physical_rows_fast)
    assert "understand_layout_core" not in source
    assert "detect_layout_parameters" not in source
    assert "build_analysis_image" not in source
    assert "detect_ordinary_symbol_entries" not in source
    assert "detect_ordinary_large_head_entries" not in source


def test_unlined_export_worker_is_replaced_by_physical_fast_path():
    from picture_capture import unlined_line_export as exporter
    from picture_capture.unlined_fast_path_runtime import (
        export_unlined_page_job_fast,
        install_unlined_fast_path,
    )
    from picture_capture.unlined_physical_rows_resolver import (
        resolve_unlined_physical_rows,
    )

    install_unlined_fast_path()
    assert exporter.export_unlined_page_job is export_unlined_page_job_fast
    source = inspect.getsource(export_unlined_page_job_fast)
    assert "resolve_unlined_physical_rows" in source
    assert "understand_layout_core" not in source
    assert "build_analysis_image" not in source

    resolver_source = inspect.getsource(resolve_unlined_physical_rows)
    assert "understand_layout_core" not in resolver_source
    assert "detect_ordinary_symbol_entries" not in resolver_source
    assert "detect_ordinary_large_head_entries" not in resolver_source
    # Reliable detector escalation is permitted only through physical policy.
    assert "infer_dictionary_page_layout" in resolver_source


def test_gui_and_worker_composition_seed_layout_rows_for_future_qa():
    root = Path(__file__).resolve().parents[1]
    gui = (
        root / "src" / "picture_capture" / "bootstrap" / "gui.py"
    ).read_text(encoding="utf-8")
    worker = (
        root / "src" / "picture_capture" / "bootstrap" / "worker.py"
    ).read_text(encoding="utf-8")
    spawn = (
        root / "src" / "picture_capture" / "spawn_detection_runtime.py"
    ).read_text(encoding="utf-8")

    assert "install_layout_rows_persistence_runtime()" in gui
    assert "install_unlined_fast_path()" in gui
    assert gui.index("install_unlined_fast_path()") < gui.index(
        "install_unlined_line_export_ui(app_module)"
    )
    assert "install_layout_rows_persistence_runtime()" in worker
    assert "with services.capture_layout_rows(" in spawn
    assert "install_layout_rows_persistence_runtime()" not in spawn
