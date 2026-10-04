from __future__ import annotations

from pathlib import Path

from picture_capture.app import UsageGuideWindow as AppUsageGuideWindow
from picture_capture.ui.dialogs.usage_guide import UsageGuideWindow


ROOT = Path(__file__).resolve().parents[1]


def test_usage_guide_has_stable_direct_import_and_app_compatibility_alias() -> None:
    assert AppUsageGuideWindow is UsageGuideWindow
    assert UsageGuideWindow.__module__ == "picture_capture.ui.dialogs.usage_guide"
    assert UsageGuideWindow.PAGES
    assert UsageGuideWindow.PAGES[0][0] == "quick"


def test_usage_guide_dialog_has_no_reverse_dependency_on_app() -> None:
    source = (
        ROOT / "src" / "picture_capture" / "ui" / "dialogs" / "usage_guide.py"
    ).read_text(encoding="utf-8")
    app_source = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")

    assert "picture_capture.app" not in source
    assert "from ...app import" not in source
    assert "class UsageGuideWindow" in source
    assert "class UsageGuideWindow" not in app_source
    assert "from .ui.dialogs.usage_guide import UsageGuideWindow" in app_source
