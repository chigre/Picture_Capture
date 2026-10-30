"""R4.2 actual Tk focused opt-in controls on disposable synthetic pages (E2).

This is an automated native-Tk integration smoke, NOT a Windows human E3 or
a benchmark with real dictionary scans. It runs the real project loader,
ReviewWindow, ttk Checkbuttons, 筛选 callback and async UI workers.
"""
from __future__ import annotations

import faulthandler
import os
from pathlib import Path
import sys
import tempfile
import threading
from tkinter import ttk
from unittest.mock import patch

from picture_capture.models import AppSettings
from picture_capture.persistence.project_storage import settings_path
from picture_capture.io.formats import pdic_path, read_pdic

from gui_project_roundtrip_smoke import _sample_project, _pump_until


def check(condition, message: str):
    if not condition:
        raise AssertionError(message)


def find_controls(parent, label):
    matches = []
    pending = [parent]
    while pending:
        current = pending.pop()
        for child in current.winfo_children():
            if isinstance(child, ttk.Button) or isinstance(child, ttk.Checkbutton):
                if label in str(child.cget("text")):
                    matches.append(child)
            pending.append(child)
    check(len(matches) == 1, f"expected one native Tk control for {label!r}, got {len(matches)}")
    return matches[0]


def run():
    from picture_capture.bootstrap.application import build_application

    module = build_application()
    with tempfile.TemporaryDirectory(prefix="pc-g3-r4-tk-") as tmp:
        root = (Path(tmp) / "synthetic-project").resolve()
        page1, page2 = _sample_project(root)
        before_image = [p.read_bytes() for p in (page1, page2)]
        app = module.PictureCaptureApp()
        review = None
        try:
            app.withdraw()
            with patch.object(
                module.messagebox, "showerror",
                side_effect=AssertionError("unexpected Tk modal on project load"),
            ):
                app._load_project(root)
                _pump_until(
                    app, lambda: app.project is not None
                    and app.current_page == page1 and app.image is not None,
                    seconds=35, description="G3 focused Tk fixture project load",
                )
            check(
                not any((
                    app.settings.focused_review_risk_queue_enabled,
                    app.settings.focused_review_risk_witness_capture,
                    app.settings.focused_review_timing_enabled,
                )), "fresh synthetic AppSettings unexpectedly opted in",
            )
            review = module.ReviewWindow(app)
            review.update()
            if not review.focused_panel_expanded.get():
                review._toggle_focused_panel()
                review.update()
            toggles = (
                ("已核验来源的高风险优先", "focused_risk_priority_var",
                 "focused_review_risk_queue_enabled"),
                ("下次 OCR 批量画线记录来源证明", "focused_risk_capture_var",
                 "focused_review_risk_witness_capture"),
                ("记录本次筛选阶段耗时", "focused_timing_var",
                 "focused_review_timing_enabled"),
            )
            controls = []
            for label, variable, field in toggles:
                checkbox = find_controls(review.focused_panel_body, label)
                check(
                    not getattr(review, variable).get()
                    and not getattr(app.settings, field),
                    f"{field} did not default OFF in the native Tk UI",
                )
                checkbox.invoke()
                review.update()
                check(getattr(review, variable).get(), f"{field} native Checkbutton did not toggle")
                controls.append(checkbox)

            action = find_controls(review.focused_panel_body, "筛选")
            review.focused_page_range_var.set("1")
            review.focused_include_mismatch_var.set(False)
            review.focused_include_characters_var.set(True)
            review.focused_exclude_single_var.set(False)
            review.focused_exclude_reference_var.set(False)
            review.focused_characters_var.set("")

            # A rejected filter must not persist any of the three opt-ins,
            # start a worker, mutate PDIC, or produce a witness sidecar.
            baseline_settings = settings_path(root).read_bytes()
            baseline_pdic = pdic_path(page1).read_bytes()
            shown = []
            with patch.object(
                module.messagebox, "showinfo",
                side_effect=lambda title, *_a, **_kw: shown.append(title),
            ):
                action.invoke()
            review.update()
            check(shown == ["特定字符为空"], "native Tk empty-token refusal did not reach its callback")
            check(settings_path(root).read_bytes() == baseline_settings,
                  "invalid Tk filter published settings")
            check(pdic_path(page1).read_bytes() == baseline_pdic,
                  "invalid Tk filter rewrote user PDIC")
            check(not review._filter_rows_active, "invalid Tk filter started scanning")

            # The real success path persists explicit options and executes
            # an OCR-free page filter. Old OCR caches remain un-attested.
            review.focused_characters_var.set("synthetic")
            action.invoke()
            _pump_until(
                app,
                lambda: review._filter_scan_complete
                and len(review.filtered_targets) == 2,
                seconds=35, description="G3 focused first native Tk scan",
            )
            check(
                [(x["original_word"],x["x"],x["y"]) for x in review.filtered_targets]
                == [("synthetic-alpha", 80, 76), ("synthetic-beta", 85, 182)],
                "no-witness option re-ordered synthetic source positions",
            )
            check(
                "扫描" in review.focused_timing_summary_var.get()
                and review._focused_timing_session is not None,
                "opted-in local aggregate timing not shown in native UI",
            )
            loaded = AppSettings.from_json(settings_path(root))
            for _label, _variable, field in toggles:
                check(getattr(loaded, field) is True,
                      f"successful Tk filter did not persist explicit {field}")
            origin = root / "QT" / "PaddleOCR" / "synthetic-001_risk_origin_v1.json"
            check(not origin.exists(), "enabling next OCR witness retroactively created evidence")

            # Re-filter while a human edit is pending must not persist newly
            # unchecked options nor replace already-visible editing targets.
            previous_list = review.filtered_targets
            review._filter_pending_changes[0] = {
                (80, 76): {
                    "page_index": 0, "x": 80, "y": 76,
                    "original_word": "synthetic-alpha", "new_word": "pending",
                }
            }
            for checkbox in controls:
                checkbox.invoke()
            blocked_settings = settings_path(root).read_bytes()
            action.invoke()
            review.update()
            check(review.filtered_targets is previous_list,
                  "pending edit was erased/replaced by rejected re-filter")
            check(settings_path(root).read_bytes() == blocked_settings,
                  "blocked native re-filter silently saved new options")
            check(review._filter_pending_changes[0][(80, 76)]["new_word"] == "pending",
                  "pending human edit vanished during blocked Tk re-filter")
            review._filter_pending_changes.clear()

            check([p.read_bytes() for p in (page1, page2)] == before_image,
                  "native UI smoke unexpectedly modified synthetic source image")
            check(
                [(e.word, e.x, e.y) for e in read_pdic(pdic_path(page1))]
                == [("synthetic-alpha", 80, 76), ("synthetic-beta", 85, 182)],
                "synthetic Tk filter changed saved PDIC words/source XY",
            )
            print("G3 R4.2 native Tk focused options + refusal smoke: OK", flush=True)
        finally:
            if review is not None:
                review._filter_pending_changes.clear()
                review.destroy()
            app.destroy()


def main() -> int:
    finished = threading.Event()

    def watchdog() -> None:
        if finished.wait(95):
            return
        print("G3 focused Tk smoke watchdog TIMEOUT", file=sys.stderr, flush=True)
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        os._exit(124)

    threading.Thread(target=watchdog, name="g3-r4-tk-watchdog", daemon=True).start()
    try:
        run()
    finally:
        finished.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
