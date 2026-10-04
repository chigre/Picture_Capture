from __future__ import annotations

from pathlib import Path

from picture_capture.app import _build_modern_dialog_heading as AppDialogHeading
from picture_capture.ui.dialogs.common import _build_modern_dialog_heading


ROOT = Path(__file__).resolve().parents[1]


def test_shared_dialog_heading_keeps_app_compatibility_alias() -> None:
    assert AppDialogHeading is _build_modern_dialog_heading
    assert _build_modern_dialog_heading.__module__ == "picture_capture.ui.dialogs.common"


def test_shared_dialog_helper_has_no_reverse_dependency_on_app() -> None:
    source = (
        ROOT / "src" / "picture_capture" / "ui" / "dialogs" / "common.py"
    ).read_text(encoding="utf-8")
    app_source = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")

    assert "picture_capture.app" not in source
    assert "from ...app import" not in source
    assert "def _build_modern_dialog_heading" in source
    assert "def _build_modern_dialog_heading" not in app_source
    assert "from .ui.dialogs.common import _build_modern_dialog_heading" in app_source
