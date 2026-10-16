"""Real Tk widget smoke for the R3 OCR-owned delete persistence boundary.

Runs only on a generated synthetic page; not real Windows human acceptance.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import faulthandler
import os
import sys
import tempfile
import threading
import tkinter as tk

from PIL import Image

from picture_capture.formats import pdic_path, read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.project_storage import simplified_review_path_for_image
from picture_capture import proofreading_transactions as tx
from picture_capture.ui.review_candidate_delete_actions import (
    delete_owned_review_candidate,
)
from picture_capture.ui.review_transaction_actions import _history


def run() -> None:
    with tempfile.TemporaryDirectory(prefix="picture-capture-r3-tk-") as temp:
        folder = Path(temp)
        page = folder / "synthetic.png"
        with Image.new("RGB", (300, 240), "white") as image:
            image.save(page)
        head = Entry("head", 10, 40, candidate_id="ocr-owned")
        other = Entry("other", 20, 120)
        entries = [head, other]
        write_pdic(pdic_path(page), entries, 300, ("synthetic", "@", "@"))
        directory = folder / "QT" / "PaddleOCR"
        directory.mkdir(parents=True)
        manual = directory / "synthetic_manual_selection.json"
        ocr = directory / "synthetic.json"
        simplified = simplified_review_path_for_image(page)
        candidate = {"candidate_id": "ocr-owned", "selected": True,
                     "word": "head", "source_x": 10, "source_y": 40}
        root = tk.Tk()
        try:
            root.title("R3 candidate transaction synthetic GUI smoke")
            root.geometry("400x180+20+20")
            status = tk.StringVar(root, value="")
            checker = tk.BooleanVar(root, value=True)
            vars_ = [tk.StringVar(root, value=row.word) for row in entries]
            app = SimpleNamespace(
                current_page=page, current_index=0, entries=entries,
                project=SimpleNamespace(root=folder),
                settings=SimpleNamespace(proofreading_event_capture=False),
                _batch_active=False, _pending_manual_override_payload=None,
                _manual_selection_path=lambda: manual,
                _paddle_cache_path=lambda: ocr,
                ocr_review_candidates=[candidate],
                candidate_check_vars={"ocr-owned": checker}, status_var=status,
                _sort_entries_reading_order=lambda: None,
                _refresh_word_fill_check_from_line_count=lambda *a, **kw: None,
                _update_page_row=lambda *a: None,
                clear_review_entry_highlight=lambda: None,
                redraw=lambda: None,
            )
            review = SimpleNamespace(
                parent=app, _filter_rows_active=False,
                _rendered_page_stem=page.stem, vars=vars_,
                _simplified_dirty_pages=set(), _simplified_page_cache={},
                active_index=0, _request_render_rows=lambda **kw: None,
                _show_ocr_options=lambda *a: None,
                _update_title=lambda: None,
            )
            review._bound_row_entries = lambda: app.entries
            field = tk.Entry(root, textvariable=vars_[0])
            field.pack()
            tk.Checkbutton(root, text="OCR candidate", variable=checker).pack()
            command = lambda: delete_owned_review_candidate(review, 0, app.entries)
            button = tk.Button(root, text="Delete candidate", command=command)
            button.pack()
            tk.Label(root, textvariable=status).pack()
            root.update()

            field.focus_set()
            root.update()
            # An unsaved focused edit must refuse without any file mutation.
            field.insert("end", " unsaved")
            root.update()
            before = pdic_path(page).read_bytes()
            button.invoke()
            root.update()
            assert pdic_path(page).read_bytes() == before
            assert checker.get() and candidate["selected"] is True
            assert not manual.exists()

            vars_[0].set("head")
            root.update()
            button.invoke()
            root.update()
            assert [e.word for e in read_pdic(pdic_path(page))] == ["other"]
            assert app.entries == [other] and head not in app.entries
            assert not checker.get() and candidate["selected"] is False
            assert manual.exists()
            assert not tx._recovery_path(page).exists()
            assert page.exists() and not simplified.exists()

            # Real Tk variables must rebind after a candidate-owned delete.
            committed = pdic_path(page).read_bytes()
            review.vars = [tk.StringVar(root, value=row.word) for row in app.entries]
            assert _history(review).undo(review)
            assert pdic_path(page).read_bytes() == before
            assert app.entries == [head, other]
            assert candidate["selected"] is True and checker.get()
            assert not manual.exists()
            review.vars = [tk.StringVar(root, value=row.word) for row in app.entries]
            assert _history(review).redo(review)
            assert pdic_path(page).read_bytes() == committed
            assert app.entries == [other]
            assert candidate["selected"] is False and not checker.get()
            assert manual.exists()
            review.vars = vars_

            # A fresh page can retry after failed disk publication; no stale
            # GUI checkbox or list membership changes before durability.
            app.entries[:] = [head, other]
            vars_[0].set("head")
            candidate["selected"] = True
            checker.set(True)
            manual.unlink()
            write_pdic(pdic_path(page), app.entries, 300, ("synthetic", "@", "@"))
            prior = pdic_path(page).read_bytes()
            publish = tx._publish
            failed = False

            def one_failure(path, data):
                nonlocal failed
                if path == manual and not failed:
                    failed = True
                    raise OSError("injected failure")
                return publish(path, data)

            with patch.object(tx, "_publish", side_effect=one_failure):
                button.invoke()
                root.update()
            assert pdic_path(page).read_bytes() == prior
            assert app.entries == [head, other]
            assert checker.get() and candidate["selected"] is True
            assert not manual.exists()
            assert not tx._recovery_path(page).exists()
            print("R3 candidate deletion synthetic real-Tk smoke: OK", flush=True)
        finally:
            root.destroy()


def main() -> int:
    completed = threading.Event()

    def watchdog() -> None:
        if completed.wait(75):
            return
        print("R3 candidate transaction Tk smoke TIMEOUT", file=sys.stderr, flush=True)
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        os._exit(124)

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        run()
    finally:
        completed.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
