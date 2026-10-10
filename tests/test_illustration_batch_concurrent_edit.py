"""Batch-edit policy regression tests: PPP detection must not lock PDIC."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_illustration_detection_enables_navigation_and_pdic_without_ppp_editing():
    src = (ROOT / "ui" / "controllers" / "illustration.py").read_text(encoding="utf-8")
    start = src.index("    def detect_illustrations_selected_scope(")
    body = src[start:]
    assert "allow_page_navigation=True" in body
    assert "allow_pdic_edits=True" in body


def test_parallel_and_one_worker_paths_pass_permissions_through():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("    def _start_parallel_batch_task(")
    end = source.index("\n    def _poll_batch_queue(", start)
    segment = source[start:end]
    assert "allow_pdic_edits=allow_pdic_edits" in segment
    assert "allow_page_navigation=allow_page_navigation" in segment
    assert "self._batch_allow_pdic_edits = bool(allow_pdic_edits)" in segment
    assert "self._batch_allow_page_navigation = bool(allow_page_navigation)" in segment


def test_pdic_batch_mode_rejects_ppp_edits_and_save_paths():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("    def _claim_page_for_manual_edit(")
    end = source.index("\n    def _can_save_current_during_batch_navigation(", start)
    assert 'self._batch_allow_pdic_edits' in source[start:end]
    start = source.index("    def toggle_polygon_drawing(")
    end = source.index("\n    def ", start + 10)
    assert "self._batch_allow_pdic_edits" in source[start:end]
    start = source.index("    def _save_current_page_by_mode(")
    end = source.index("\n    def ", start + 10)
    assert 'and not getattr(self, "_batch_allow_pdic_edits", False)' in source[start:end]
    assert "self.save_pdic(silent=True" in source[start:end]


def test_other_batch_tasks_remain_conservative_by_default():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "allow_page_navigation: bool = False" in source
    assert "allow_pdic_edits: bool = False" in source
    assert "self._batch_allow_pdic_edits = False" in source
