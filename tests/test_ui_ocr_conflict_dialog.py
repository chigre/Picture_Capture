from __future__ import annotations

from pathlib import Path

from picture_capture.app import OCRConflictReviewDialog as AppOCRConflictReviewDialog
from picture_capture.ui.dialogs.ocr_conflict import OCRConflictReviewDialog


ROOT = Path(__file__).resolve().parents[1]


def test_ocr_conflict_dialog_has_stable_direct_import_and_app_alias() -> None:
    assert AppOCRConflictReviewDialog is OCRConflictReviewDialog
    assert OCRConflictReviewDialog.__module__ == "picture_capture.ui.dialogs.ocr_conflict"


def test_ocr_conflict_dialog_has_no_reverse_dependency_on_app() -> None:
    source = (
        ROOT / "src" / "picture_capture" / "ui" / "dialogs" / "ocr_conflict.py"
    ).read_text(encoding="utf-8")
    app_source = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")

    assert "picture_capture.app" not in source
    assert "from ...app import" not in source
    assert "class OCRConflictReviewDialog" in source
    assert "class OCRConflictReviewDialog" not in app_source
    assert "from .ui.dialogs.ocr_conflict import OCRConflictReviewDialog" in app_source
