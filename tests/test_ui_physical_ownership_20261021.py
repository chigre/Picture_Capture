"""Issue #562: UI implementation owners are physical, not root shims."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
UI_OWNERS = (
    "appearance",
    "environment_center",
    "unicode_nonbmp_input",
    "layout_visualization_ui",
    "layout_visualization_ui_v2",
)


@pytest.mark.parametrize("name", UI_OWNERS)
def test_ui_owner_is_physical_without_old_root_alias(name: str) -> None:
    assert not (PACKAGE / (name + ".py")).exists()
    assert (PACKAGE / "ui" / (name + ".py")).is_file()
    assert importlib.util.find_spec("picture_capture." + name) is None
    assert importlib.util.find_spec("picture_capture.ui." + name) is not None


def test_high_risk_layout_v3_and_historical_compatibility_remain_at_root() -> None:
    for name in ("layout_visualization_ui_v3", "ui_terminology", "settings_help_restore"):
        assert (PACKAGE / (name + ".py")).is_file()
