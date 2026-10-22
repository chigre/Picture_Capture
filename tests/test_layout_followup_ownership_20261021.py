"""Issue #562: Layout ownership is physical and import paths are stable."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
OWNERS = {
    "boundary_placement": "boundary_placement",
    "layout_profile_anchor": "profile_anchor",
    "layout_composition": "composition",
    "page_x_registration": "page_x_registration",
    "layout_visualization_shared": "visualization_shared",
    "layout_visualization_summary": "visualization_summary",
}

@pytest.mark.parametrize("old, new", sorted(OWNERS.items()))
def test_no_legacy_root_layout_shim(old: str, new: str) -> None:
    assert not (PACKAGE / (old + ".py")).exists()
    assert (PACKAGE / "layout" / (new + ".py")).is_file()
    assert importlib.util.find_spec("picture_capture." + old) is None
    assert importlib.util.find_spec("picture_capture.layout." + new) is not None


def test_retained_layout_entrypoints_are_untouched() -> None:
    assert not (PACKAGE / "layout_rows_cache.py").exists()
    assert (PACKAGE / "layout/rows_cache.py").is_file()
    assert not (PACKAGE / "layout_detection.py").exists()
    assert (PACKAGE / "layout/detection.py").is_file()
    for former, owner in (("layout_core_understanding", "core_understanding"),
                          ("layout_physical_indent", "physical_indent"),
                          ("layout_detection_legacy", "detector_legacy")):
        assert not (PACKAGE / (former + ".py")).exists()
        assert (PACKAGE / "layout" / (owner + ".py")).is_file()
        assert importlib.util.find_spec("picture_capture." + former) is None
        assert importlib.util.find_spec("picture_capture.layout." + owner) is not None


def test_step_replay_ui_physical_owner():
    assert not (PACKAGE / "layout_step_replay_ui.py").exists()
    assert (PACKAGE / "ui/layout_step_replay.py").is_file()


def test_layout_visualization_ui_has_physical_ui_owner() -> None:
    assert not (PACKAGE / "layout_visualization_ui.py").exists()
    assert (PACKAGE / "ui/layout_visualization_ui.py").is_file()
