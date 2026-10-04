from __future__ import annotations

from pathlib import Path

from picture_capture.app import OldNewComparisonWindow as AppOldNewComparisonWindow
from picture_capture.ui.dialogs.old_new_comparison import OldNewComparisonWindow


ROOT = Path(__file__).resolve().parents[1]


def test_old_new_comparison_has_stable_direct_import_and_app_alias() -> None:
    assert AppOldNewComparisonWindow is OldNewComparisonWindow
    assert OldNewComparisonWindow.__module__ == "picture_capture.ui.dialogs.old_new_comparison"
    assert OldNewComparisonWindow.FILTERS == ("全部差异", "新增", "删除", "修改")


def test_old_new_comparison_has_no_reverse_dependency_on_app() -> None:
    source = (
        ROOT / "src" / "picture_capture" / "ui" / "dialogs" / "old_new_comparison.py"
    ).read_text(encoding="utf-8")
    app_source = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")

    # The dialog owns its implementation; app.py only keeps the compatibility alias.
    assert "picture_capture.app" not in source
    assert "from ...app import" not in source
    assert "class OldNewComparisonWindow" in source
    assert "class OldNewComparisonWindow" not in app_source
    assert "from .ui.dialogs.old_new_comparison import OldNewComparisonWindow" in app_source
