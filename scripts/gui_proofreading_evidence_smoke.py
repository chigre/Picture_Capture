"""B2 Tk integration smoke with synthetic image/PDIC; no dictionary content.

Unlike GUI construction-only smoke, this uses real Tk widgets and callback
invocations to exercise the local evidence consent flow. It is *not* a human
acceptance test and makes no claim about real scanner image quality.
"""
from __future__ import annotations

import faulthandler
from pathlib import Path
import os
import sys
import tempfile
import threading
import tkinter as tk
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from PIL import Image, ImageDraw

from picture_capture.formats import pdic_path, write_pdic
from picture_capture.models import Entry
from picture_capture.project_storage import data_root
from picture_capture.proofreading_capture import _project_identity
from picture_capture.proofreading_events import (
    append_event, load_events, make_event, sha256_file,
)
from picture_capture.proofreading_verify_ui import (
    ProofreadingVisualVerificationDialog, journal_for_existing_page,
)


def _sample(root: Path):
    page = root / "synthetic.png"
    image = Image.new("RGB", (640, 410), "white")
    try:
        draw = ImageDraw.Draw(image)
        for y in (90, 220):
            draw.rectangle((80, y, 300, y + 5), fill="black")
        image.save(page)
    finally:
        image.close()
    pdic = pdic_path(page)
    write_pdic(
        pdic, [Entry("synthetic-first", 80, 90),
               Entry("synthetic-second", 180, 220)],
        50, ("synthetic", "@", "@"),
    )
    _project_identity(root)
    journal = (
        data_root(root) / "ProofreadingEvidence"
        / f"{uuid5(NAMESPACE_URL, page.name).hex}.json"
    )
    operations = []
    for i, (word, x, y) in enumerate((
        ("synthetic-first", 80, 90),
        ("synthetic-second", 180, 220),
    )):
        event = make_event(
            page_id=f"synthetic/{page.name}",
            action="rename",
            before={"word": f"old-{i}", "x": x, "y": y},
            after={"word": word, "x": x, "y": y},
            entry_id=f"synthetic-stable-{i}",
            pdic_sha256=sha256_file(pdic),
            image_sha256=sha256_file(page),
        )
        append_event(journal, event, pdic_file=pdic)
        operations.append(event["operation_id"])
    return page, pdic, journal, operations


def _select(dialog: ProofreadingVisualVerificationDialog, op_id: str, root: tk.Tk):
    dialog.table.selection_set(op_id)
    dialog.table.event_generate("<<TreeviewSelect>>")
    root.update()
    assert dialog._selected_id == op_id, "Treeview did not select operation"
    assert dialog._preview_valid and dialog.preview_photo is not None, (
        "Original synthetic scan crop was not displayed"
    )
    assert not dialog.confirmed.get(), "Changing selection must reset consent"
    assert dialog.positive.instate(("disabled",))
    assert dialog.negative.instate(("disabled",))
    dialog.checkbox.invoke()
    root.update()
    assert dialog.confirmed.get(), "Explicit consent checkbox did not toggle"
    assert dialog.positive.instate(("!disabled",))
    assert dialog.negative.instate(("!disabled",))


def run() -> None:
    with tempfile.TemporaryDirectory(prefix="picture-capture-b2-gui-") as temp:
        project_root = Path(temp)
        page, pdic, journal, (first, second) = _sample(project_root)
        original_image = page.read_bytes()
        original_pdic = pdic.read_bytes()
        root = tk.Tk()
        dialog = None
        try:
            root.title("Synthetic proofreading dialog integration smoke")
            root.geometry("320x130+20+20")
            root.update()
            assert journal_for_existing_page(project_root, page) == journal

            dialog = ProofreadingVisualVerificationDialog(
                root, project_root=project_root, page=page,
            )
            root.update()
            assert len(dialog.table.get_children()) == 2
            assert dialog._selected_id is None
            assert dialog.positive.instate(("disabled",))
            assert len(load_events(journal)) == 2, "Dialog must start read-only"

            # Preview + checkbox + explicit final confirmation are mandatory.
            _select(dialog, first, root)
            unconfirmed_journal = journal.read_bytes()
            with patch(
                "picture_capture.proofreading_verify_ui.messagebox.askyesno",
                return_value=False,
            ):
                dialog.positive.invoke()
                root.update()
            assert journal.read_bytes() == unconfirmed_journal, (
                "Cancelled confirmation wrote evidence"
            )

            with (
                patch(
                    "picture_capture.proofreading_verify_ui.messagebox.askyesno",
                    return_value=True,
                ),
                patch(
                    "picture_capture.proofreading_verify_ui.messagebox.showinfo",
                ),
                patch(
                    "picture_capture.proofreading_verify_ui.messagebox.showerror",
                ) as errors,
            ):
                dialog.positive.invoke()
                root.update()
                assert not errors.called, "Valid synthetic consent failed"
            verified = [e for e in load_events(journal) if e["action"] == "verify"]
            assert len(verified) == 1
            assert verified[0]["after"]["judgment"] == "correct_headword"
            assert list(dialog.table.get_children()) == [second]

            # Source bytes changing after the preview must fail closed.
            _select(dialog, second, root)
            with Image.open(page) as opened:
                changed = opened.convert("RGB")
            try:
                changed.putpixel((0, 0), (9, 9, 9))
                changed.save(page)
            finally:
                changed.close()
            with (
                patch(
                    "picture_capture.proofreading_verify_ui.messagebox.askyesno",
                    return_value=True,
                ),
                patch(
                    "picture_capture.proofreading_verify_ui.messagebox.showerror",
                ) as errors,
            ):
                dialog.negative.invoke()
                root.update()
                assert errors.called, "Changed original scan was accepted"
            assert len([e for e in load_events(journal) if e["action"] == "verify"]) == 1

            page.write_bytes(original_image)
            dialog._reload()
            root.update()
            _select(dialog, second, root)
            with (
                patch(
                    "picture_capture.proofreading_verify_ui.messagebox.askyesno",
                    return_value=True,
                ),
                patch(
                    "picture_capture.proofreading_verify_ui.messagebox.showinfo",
                ),
                patch(
                    "picture_capture.proofreading_verify_ui.messagebox.showerror",
                ) as errors,
            ):
                dialog.negative.invoke()
                root.update()
                assert not errors.called, "Negative synthetic consent failed"
            verified = [e for e in load_events(journal) if e["action"] == "verify"]
            assert len(verified) == 2
            assert {e["after"]["judgment"] for e in verified} == {
                "correct_headword", "not_headword",
            }
            dialog.destroy()
            dialog = None
            root.update()

            # Reopening the widget reads persisted verified history, no replay.
            dialog = ProofreadingVisualVerificationDialog(
                root, project_root=project_root, page=page,
            )
            root.update()
            assert not dialog.table.get_children(), (
                "Verified operations became actionable after reopening"
            )
            assert page.read_bytes() == original_image
            assert pdic.read_bytes() == original_pdic
            assert len(load_events(journal)) == 4
            assert not journal.with_name(journal.name + ".lock").exists()
            print("B2 synthetic Tk proofreading evidence smoke: OK", flush=True)
        finally:
            if dialog is not None:
                dialog.destroy()
            root.destroy()


def main() -> int:
    completed = threading.Event()

    def watchdog() -> None:
        if completed.wait(75):
            return
        print("B2 GUI smoke watchdog TIMEOUT", file=sys.stderr, flush=True)
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
