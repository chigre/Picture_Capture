from __future__ import annotations

import inspect

from picture_capture.layout_row_recovery_runtime import (
    install_layout_row_recovery_runtime,
    logical_slots_without_loss,
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


def test_runtime_replaces_physical_indent_fallback():
    from picture_capture import layout_physical_indent as physical

    install_layout_row_recovery_runtime()

    assert physical._logical_slots_for_oversized_run is logical_slots_without_loss


def test_gui_and_spawn_paths_install_long_band_recovery():
    from picture_capture.bootstrap import gui as gui_bootstrap
    from picture_capture import spawn_detection_runtime

    gui_source = inspect.getsource(gui_bootstrap.prepare_gui_application)
    spawn_source = inspect.getsource(spawn_detection_runtime.detect_entries_job_with_runtime)

    assert "install_layout_row_recovery_runtime" in gui_source
    assert "install_layout_row_recovery_runtime" in spawn_source
