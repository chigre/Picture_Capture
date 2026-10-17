"""PDIC remains editable only when a batch explicitly opts in.

Read-only line exporters allow concurrent PDIC edits; PDIC-writing refiners
and OCR workers use page ownership to prevent a worker overwriting an edit.
"""
from pathlib import Path
from threading import Lock
from types import SimpleNamespace

from picture_capture.app import PictureCaptureApp
from picture_capture.ui.controllers.illustration import IllustrationController

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


class Status:
    def __init__(self):
        self.messages = []

    def set(self, message):
        self.messages.append(message)


def body_between(source, start, end):
    return source.split(start, 1)[1].split(end, 1)[0]


def test_lined_and_unlined_exports_opt_into_pdic_edit_without_claiming_pages():
    src = (ROOT / "ui/controllers/crop.py").read_text(encoding="utf-8")
    lined = body_between(
        src, "    def split_single_lines_selected_scope(",
        "    def export_unlined_rows_selected_scope(",
    )
    unlined = body_between(
        src, "    def export_unlined_rows_selected_scope(",
        "    def split_lines_current(",
    )
    for segment in (lined, unlined):
        assert "app._start_parallel_batch_task(" in segment
        assert "allow_pdic_edits=True," in segment
        assert "foreground_page_edit=True" not in segment
        assert "max_workers=workers" in segment
    # Both workers are read-only consumers of atomic on-disk PDIC revisions.
    source = (ROOT / "single_line_parallel.py").read_text(encoding="utf-8")
    assert "formats.read_pdic(formats.pdic_path(image_path))" in source
    source = (ROOT / "unlined_line_export.py").read_text(encoding="utf-8")
    assert "formats.read_pdic(formats.pdic_path(image_path))" in source


def test_pdic_writing_refiner_and_ocr_both_use_page_ownership():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    refiner = body_between(
        src, "    def refine_lines_selected_scope(",
        "    def ocr_ordinary_lines_text_selected_scope(",
    )
    only_ocr = body_between(
        src, "    def ocr_ordinary_lines_text_selected_scope(",
        "    def _detect_pages(",
    )
    detector = (ROOT / "ui/controllers/detection.py").read_text(encoding="utf-8")
    batch_ocr = body_between(
        detector, "    def batch_ocr(", "    def run_ocr_draw(",
    )
    assert "foreground_page_edit=True, allow_pdic_edits=True," in refiner
    assert "_start_parallel_batch_task(" in refiner
    assert "commit_refined_page_result" in refiner
    for segment in (only_ocr, batch_ocr):
        assert "foreground_page_edit=True, allow_pdic_edits=True," in segment
        assert "_start_batch_task(" in segment
    # A final blanket reload would discard proofreading performed after a
    # worker finishes, so only the page-completion event may reload the page.
    assert "save_result" in refiner
    assert "and not self._batch_foreground_pages" in only_ocr
    assert 'not getattr(app, "_batch_foreground_pages", False)' in batch_ocr


def test_manual_claim_skips_pending_worker_and_blocks_processing_page():
    status = Status()
    app = SimpleNamespace(
        _batch_active=True, _batch_foreground_pages=True,
        _batch_state_lock=Lock(),
        _batch_page_states={0: "processing", 1: "pending", 2: "done"},
        current_index=1, status_var=status,
        _update_page_row=lambda i: None,
    )
    claim = PictureCaptureApp._claim_page_for_manual_edit
    assert claim(app, 0) is False
    assert app._batch_page_states[0] == "processing"
    assert claim(app, 1) is True
    assert app._batch_page_states[1] == "manual_locked"
    assert claim(app, 2) is True
    assert "人工锁定" in status.messages[-1]
    app._foreground_batch_state = lambda index: app._batch_page_states[index]
    app.current_index = 0
    assert PictureCaptureApp._can_save_current_during_batch_navigation(app) is False
    app.current_index = 1
    assert PictureCaptureApp._can_save_current_during_batch_navigation(app) is True


def test_batch_autosave_saves_pdic_without_touching_ppp():
    written = []
    status = Status()
    app = SimpleNamespace(
        autosave_job=7, autosave_var=SimpleNamespace(get=lambda: True),
        _batch_active=True, _batch_foreground_pages=False,
        _can_save_current_during_batch_navigation=lambda: True,
        project=object(), current_page=Path("001.png"),
        _last_pdic_write_changed=False, review_window=None,
        save_pdic=lambda silent=False: written.append("pdic"),
        _save_normalized_ppp=lambda: (_ for _ in ()).throw(
            AssertionError("PPP cannot autosave during an active batch")
        ),
        status_var=status, toggle_autosave=lambda: written.append("rescheduled"),
    )
    PictureCaptureApp.autosave_tick(app)
    assert written == ["pdic", "rescheduled"]


def test_central_ppp_editor_rejects_batch_write_even_when_pdic_is_editable():
    status = Status()
    app = SimpleNamespace(
        _batch_active=True, _batch_allow_pdic_edits=True,
        current_page=Path("001.png"),
        status_var=status,
    )
    assert IllustrationController(app).persist_current() is False
    assert "禁止修改 PPP" in status.messages[-1]
