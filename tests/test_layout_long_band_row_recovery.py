from __future__ import annotations

from pathlib import Path

from picture_capture.layout_physical_indent import (
    _logical_slots_for_oversized_run as logical_slots_without_loss,
)


def test_ten_line_high_continuous_band_is_not_limited_to_four_slots():
    slots = logical_slots_without_loss(0, 400, 40.0)

    assert len(slots) == 10
    assert slots[0][0] == 0
    assert slots[-1][1] == 400
    assert all(1 <= end - start <= 76 for start, end in slots)


def test_long_page_band_stays_within_projection_acceptance_height():
    slots = logical_slots_without_loss(0, 4440, 37.0)

    assert len(slots) > 4
    assert slots[0][0] == 0
    assert slots[-1][1] == 4440
    assert all(end - start <= 37.0 * 1.90 for start, end in slots)


def test_physical_indent_statically_owns_long_band_fallback():
    root = Path(__file__).resolve().parents[1]

    assert logical_slots_without_loss.__module__ == "picture_capture.layout_physical_indent"
    assert not (root / "src/picture_capture/layout_row_recovery_runtime.py").exists()


def test_entry_paths_no_longer_install_row_recovery_runtime():
    root = Path(__file__).resolve().parents[1]
    paths = (
        "src/picture_capture/bootstrap/gui.py",
        "src/picture_capture/bootstrap/worker.py",
        "src/picture_capture/unlined_physical_rows_resolver.py",
        "src/picture_capture/layout_rows_cache.py",
    )
    for relative in paths:
        source = (root / relative).read_text(encoding="utf-8")
        assert "install_layout_row_recovery_runtime" not in source

    assert not (root / "src/picture_capture/spawn_layout_runtime.py").exists()
