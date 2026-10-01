from __future__ import annotations

import inspect

from picture_capture import launcher, ordinary_layout_worker


def test_spawn_worker_constructs_layout_primary_detector_in_child() -> None:
    source = inspect.getsource(ordinary_layout_worker.detect_entries_job)

    assert "build_ordinary_layout_primary(" in source
    assert "processing.detect_entries_job" not in source
    assert 'settings.detection_method = "left_edge"' in source


def test_launcher_rebinds_gui_ordinary_job_to_spawn_safe_worker() -> None:
    source = inspect.getsource(launcher.prepare_app_module)

    assert "ordinary_layout_worker" in source
    assert "app_module.detect_entries_job = ordinary_detect_entries_job" in source
