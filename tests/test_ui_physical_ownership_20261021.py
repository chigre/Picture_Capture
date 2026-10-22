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
    assert (PACKAGE / "layout_visualization_ui_v3.py").is_file()
    assert not (PACKAGE / "ui_terminology.py").exists()
    assert (PACKAGE / "ui" / "terminology_compat.py").is_file()


def test_refinement_batch_progress_callback_uses_existing_canonical_owner() -> None:
    from types import SimpleNamespace
    from picture_capture.refinement.progress import report_refinement_page

    app_source = (PACKAGE / "app.py").read_text(encoding="utf-8")
    assert "from .refinement.progress import report_refinement_page" in app_source
    assert "from .marker_refinement_progress import report_refinement_page" not in app_source

    status = []
    ui = SimpleNamespace(
        batch_text_var=SimpleNamespace(set=lambda value: status.append(("batch", value))),
        status_var=SimpleNamespace(set=lambda value: status.append(("status", value))),
    )
    report_refinement_page(ui, 1, 3, "001", {"skipped": True, "reason": "manual-only"})
    assert any("manual-only" in value for kind, value in status if kind == "status")
