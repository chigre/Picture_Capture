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
from picture_capture.persistence.project_storage import (
    page_sections_read_path_for_image, ppp_read_path_for_image, settings_path,
)
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
            if label == "筛选":
                if isinstance(child, ttk.Button) and str(child.cget("text")) == label:
                    matches.append(child)
            elif isinstance(child, ttk.Checkbutton) and label in str(child.cget("text")):
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

            # An early click cannot bypass R3's async initial source
            # snapshot. Simulate a not-yet-bound window even on fast runners;
            # then wait for real native source rows to finish painting.
            review.focused_characters_var.set("synthetic")
            saved_stem = review._rendered_page_stem
            review._rendered_page_stem = ""
            action.invoke()
            check(
                not review._filter_rows_active
                and settings_path(root).read_bytes() == baseline_settings,
                "not-ready R3 proofreading window started a filter or persisted settings",
            )
            review._rendered_page_stem = saved_stem
            _pump_until(
                app,
                lambda: review._rendered_page_stem == page1.stem
                and len(review.vars) == len(app.entries),
                seconds=35, description="G3 initial R3 native crop/source binding",
            )

            # A R3 source refusal must not persist new options, start any
            # filter or silently repair user-owned PDIC/manual content.
            with patch.object(
                review, "save", side_effect=RuntimeError("synthetic stale source")
            ):
                action.invoke()
            check(
                not review._filter_rows_active
                and settings_path(root).read_bytes() == baseline_settings
                and pdic_path(page1).read_bytes() == baseline_pdic,
                "failed R3 guarded save mutated setting or PDIC",
            )

            # The real success path persists explicit options and executes
            # an OCR-free page filter. Old OCR caches remain un-attested.
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

            # Native Tk invalid batch-size refusal during an active focused
            # epoch must not advance its serial, clear the current results,
            # persist newly unchecked options, or rewrite saved PDIC.
            # Exercise the actual button/error callback rather than bypassing
            # UI validation with a direct model invocation.
            pre_invalid_epoch = review._filter_scan_serial
            pre_invalid_targets = review.filtered_targets
            pre_invalid_settings = settings_path(root).read_bytes()
            pre_invalid_pdic = pdic_path(page1).read_bytes()
            previous_batch_text = review.focused_batch_size_var.get()
            review.focused_batch_size_var.set("not-an-integer")
            batch_errors = []
            with patch.object(
                module.messagebox, "showerror",
                side_effect=lambda title, *_a, **_kw: batch_errors.append(title),
            ):
                action.invoke()
            review.update()
            check(batch_errors == ["筛选条件无效"],
                  "native Tk invalid batch size was not rejected")
            check(
                review._filter_scan_serial == pre_invalid_epoch
                and review.filtered_targets is pre_invalid_targets
                and review._filter_rows_active,
                "invalid batch size replaced the active filter epoch",
            )
            check(
                settings_path(root).read_bytes() == pre_invalid_settings
                and pdic_path(page1).read_bytes() == pre_invalid_pdic,
                "invalid batch size rewrote saved settings or PDIC",
            )
            review.focused_batch_size_var.set(previous_batch_text)

            # Switching all optional controls back OFF must require a
            # successful new filter epoch, not retain stale ON preferences.
            # This also exercises a second native async scan after a
            # rejected re-filter without changing saved source data.
            prior_epoch = review._filter_scan_serial
            action.invoke()
            _pump_until(
                app,
                lambda: review._filter_scan_serial > prior_epoch
                and review._filter_scan_complete
                and len(review.filtered_targets) == 2
                and review._filter_rows_active,
                seconds=35, description="G3 native Tk opt-out rescan",
            )
            reloaded = AppSettings.from_json(settings_path(root))
            for _label, variable, field in toggles:
                check(
                    not getattr(review, variable).get()
                    and getattr(reloaded, field) is False,
                    f"successful Tk opt-out did not persist OFF for {field}",
                )
            check(
                [(x["original_word"], x["x"], x["y"]) for x in review.filtered_targets]
                == [("synthetic-alpha", 80, 76), ("synthetic-beta", 85, 182)],
                "second native filter changed original source XY or ordering",
            )
            check(not origin.exists(), "opt-out rescan unexpectedly created OCR provenance")

            # Real native Tk integration for the focused-save source owner.
            # The prior unit tests faked pending edits and worker dispatch;
            # this exercise uses the actual accepted crop, StringVar trace,
            # 160-ms autosave and background failure callback. Only a
            # disposable synthetic project is touched (NOT operator E3).
            _pump_until(
                app,
                lambda: (
                    bool(getattr(review, "filter_vars", ()))
                    and bool(review._filter_current_batch_targets)
                    and review._filter_current_batch_targets[0].get(
                        "_focused_save_source_witness"
                    ) is not None
                ),
                seconds=35,
                description="G3 native focused source-attested crop display",
            )
            target = review._filter_current_batch_targets[0]
            check(
                (int(target["page_index"]), int(target["x"]), int(target["y"]))
                == (0, 80, 76),
                "native filtered editor attached to an unexpected source coordinate",
            )
            before_drift_pdic = pdic_path(page1).read_bytes()
            before_drift_rows = [
                line.split("#") for line in before_drift_pdic.decode("utf-8").splitlines()
                if line.strip()
            ]
            check(
                len(before_drift_rows) == 2
                and all(len(fields) == 8 for fields in before_drift_rows),
                "native synthetic PDIC fixture is not two eight-field rows",
            )
            before_ppp = ppp_read_path_for_image(page1).read_bytes()
            before_settings = settings_path(root).read_bytes()
            before_main_words = [(e.word, e.x, e.y) for e in app.entries]
            section_path = page_sections_read_path_for_image(page1)
            section_original = (
                section_path.read_bytes() if section_path.is_file() else None
            )
            native_save_alerts = []
            try:
                with patch.object(
                    module.messagebox, "showerror",
                    side_effect=lambda title, message, **_kw:
                    native_save_alerts.append((title, message)),
                ):
                    # This is an actual Tk StringVar mutation, not a direct
                    # mock of _queue_focused_change or a manufactured witness.
                    review.filter_vars[0].set("synthetic-native-edit")
                    queued = review._filter_pending_changes.get(0, {}).get(
                        (80, 76)
                    )
                    check(
                        queued is not None
                        and queued.get("_focused_save_source_witness")
                        == target["_focused_save_source_witness"],
                        "Tk human change did not retain the displayed crop witness",
                    )
                    # Introduce an external SECTION after the editor's
                    # source snapshot but before the autosave worker fires.
                    # Existing JSON stays parseable if it already exists.
                    section_path.parent.mkdir(parents=True, exist_ok=True)
                    section_path.write_bytes(
                        b'{"synthetic_section_added":true}'
                        if section_original is None
                        else section_original + b" "
                    )
                    check(
                        page_sections_read_path_for_image(page1).read_bytes()
                        != (section_original if section_original is not None else b""),
                        "synthetic SECTION mutation did not take effect",
                    )
                    _pump_until(
                        app,
                        lambda: (
                            not review._filter_save_running
                            and len(native_save_alerts) == 1
                            and review._filter_pending_changes.get(0, {}).get(
                                (80, 76), {}
                            ).get("new_word") == "synthetic-native-edit"
                            and review.winfo_exists()
                        ),
                        seconds=35,
                        description="G3 native Tk stale-SECTION save refusal",
                    )
                    check(
                        pdic_path(page1).read_bytes() == before_drift_pdic,
                        "native stale-SECTION save overwrote synthetic PDIC",
                    )
                    check(
                        [(e.word, e.x, e.y) for e in app.entries]
                        == before_main_words,
                        "native failed save mutated main canvas Entry words/XY",
                    )
                    check(
                        review.filter_vars[0].get() == "synthetic-native-edit"
                        and review._filter_pending_changes[0][(80, 76)][
                            "new_word"
                        ] == "synthetic-native-edit"
                        and target["original_word"] == "synthetic-alpha"
                        and not review._filter_close_after_save,
                        "native save failure lost the human edit or closed the review",
                    )
                    check(
                        all("保存失败" in title for title, _ in native_save_alerts)
                        and "synthetic-native-edit" not in str(native_save_alerts),
                        "native save failure UI showed a headword or wrong outcome",
                    )
            finally:
                # Restore the disposable source, never a private/real page.
                if section_original is None:
                    section_path.unlink(missing_ok=True)
                else:
                    section_path.write_bytes(section_original)
                # Explicitly abandon this intentionally unsaved test edit;
                # do not allow ReviewWindow cleanup to publish it later.
                review._filter_pending_changes.clear()
                job = review._filter_save_job
                if job is not None:
                    try:
                        review.after_cancel(job)
                    except module.tk.TclError:
                        pass
                    review._filter_save_job = None

            # Retry through the SAME real Tk editor after the stale
            # SECTION has been restored to its displayed source state.
            # This positive path must really publish the word, update the
            # main canvas Entry, and preserve all other eight PDIC fields.
            # A denied save is NOT grounds to silently discard/rebind the
            # user's source XY, fabricate a new witness, or edit sidecars.
            check(
                pdic_path(page1).read_bytes() == before_drift_pdic
                and ppp_read_path_for_image(page1).read_bytes() == before_ppp,
                "failed Tk save changed original PDIC/PPP before retry",
            )
            review.filter_vars[0].set("synthetic-native-retried")
            retry_queued = review._filter_pending_changes.get(0, {}).get((80, 76))
            check(
                retry_queued is not None
                and retry_queued["original_word"] == "synthetic-alpha"
                and retry_queued["new_word"] == "synthetic-native-retried"
                and retry_queued["_focused_save_source_witness"]
                == target["_focused_save_source_witness"],
                "native Tk retry discarded displayed provenance or source XY",
            )
            _pump_until(
                app,
                lambda: (
                    not review._filter_save_running
                    and not review._filter_pending_changes
                    and target["original_word"] == "synthetic-native-retried"
                    and target["current_word"] == "synthetic-native-retried"
                    and pdic_path(page1).read_bytes() != before_drift_pdic
                ),
                seconds=35,
                description="G3 native Tk successful retry after SECTION restore",
            )
            saved_rows = [
                line.split("#")
                for line in pdic_path(page1).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            check(
                len(saved_rows) == len(before_drift_rows)
                and all(len(fields) == 8 for fields in saved_rows)
                and saved_rows[0][0] == "synthetic-native-retried"
                and saved_rows[0][1:] == before_drift_rows[0][1:]
                and saved_rows[1] == before_drift_rows[1],
                "native Tk retry changed source XY, 8-field metadata or another PDIC row",
            )
            check(
                [(e.word, e.x, e.y) for e in read_pdic(pdic_path(page1))]
                == [("synthetic-native-retried", 80, 76),
                    ("synthetic-beta", 85, 182)]
                and [(e.word, e.x, e.y) for e in app.entries]
                == [("synthetic-native-retried", 80, 76),
                    ("synthetic-beta", 85, 182)]
                and review.filter_vars[0].get() == "synthetic-native-retried"
                and target["current_word"] == "synthetic-native-retried",
                "native positive retry did not reconcile Tk, PDIC and main source XY",
            )
            check(
                ppp_read_path_for_image(page1).read_bytes() == before_ppp
                and settings_path(root).read_bytes() == before_settings
                and (section_path.read_bytes() if section_original is not None else None)
                == section_original
                and [p.read_bytes() for p in (page1, page2)] == before_image,
                "native positive retry mutated PPP, settings, SECTION or original image",
            )
            check(not origin.exists(), "retry fabricated retroactive OCR provenance")

            # Native Tk in-flight reversion race, with a real background
            # worker and TWO actual PDIC publications. Bound only the
            # source-owner writer entrypoint to hold the first background
            # worker until the foreground editor is reverted. No source
            # images or user-project paths are involved.
            before_inflight = pdic_path(page1).read_bytes()
            first_started = threading.Event()
            allow_first = threading.Event()
            worker_words = []
            real_writer = module._apply_focused_review_page_updates

            def gated_synthetic_writer(the_page, pages, index, changes):
                worker_words.append(tuple(change["new_word"] for change in changes))
                if len(worker_words) == 1:
                    first_started.set()
                    if not allow_first.wait(timeout=30):
                        raise RuntimeError("synthetic Tk concurrency gate timed out")
                return real_writer(the_page, pages, index, changes)

            try:
                with patch.object(
                    module, "_apply_focused_review_page_updates",
                    side_effect=gated_synthetic_writer,
                ):
                    review.filter_vars[0].set("synthetic-inflight-write")
                    _pump_until(
                        app,
                        lambda: first_started.is_set()
                        and review._filter_save_running,
                        seconds=35,
                        description="G3 native Tk first PDIC writer held in flight",
                    )
                    check(
                        worker_words == [("synthetic-inflight-write",)]
                        and pdic_path(page1).read_bytes() == before_inflight,
                        "in-flight worker unexpectedly published before release",
                    )
                    # The original display-time text is restored in the
                    # actual Tk StringVar while the first writer is blocked.
                    # Its old pending edit legitimately vanishes; callback
                    # must requeue it relative to the newly committed word.
                    review.filter_vars[0].set("synthetic-native-retried")
                    check(
                        not review._filter_pending_changes
                        and target["current_word"] == "synthetic-native-retried"
                        and target["original_word"] == "synthetic-native-retried",
                        "native in-flight reversion did not clear old pending edit",
                    )
                    allow_first.set()
                    _pump_until(
                        app,
                        lambda: (
                            len(worker_words) == 2
                            and worker_words[-1] == ("synthetic-native-retried",)
                            and not review._filter_save_running
                            and not review._filter_pending_changes
                            and target["original_word"] == "synthetic-native-retried"
                            and pdic_path(page1).read_bytes() == before_inflight
                        ),
                        seconds=35,
                        description="G3 native Tk reversion restored after two real PDIC saves",
                    )
            finally:
                allow_first.set()

            check(
                worker_words
                == [("synthetic-inflight-write",),
                    ("synthetic-native-retried",)]
                and [(e.word, e.x, e.y) for e in app.entries]
                == [("synthetic-native-retried", 80, 76),
                    ("synthetic-beta", 85, 182)]
                and review.filter_vars[0].get() == "synthetic-native-retried"
                and ppp_read_path_for_image(page1).read_bytes() == before_ppp
                and settings_path(root).read_bytes() == before_settings
                and (section_path.read_bytes() if section_original is not None else None)
                == section_original
                and [p.read_bytes() for p in (page1, page2)] == before_image
                and not origin.exists(),
                "native in-flight revert lost edit, modified sidecars, or changed source XY",
            )
            print("G3 R4.2 native Tk focused refusal + successful retry + in-flight reversion: OK", flush=True)

            # Review-close safety must also exercise the actual ReviewWindow
            # callback, not only the synthetic SimpleNamespace unit owner.
            # First verify ordinary R3 close refuses a sensitive exception
            # without leaking its path/headword into Tk status or dialogs.
            ordinary_close_alerts = []
            review._filter_rows_active = False
            try:
                with patch.object(
                    review, "save",
                    side_effect=OSError(
                        "PRIVATE_NATIVE_PATIENT_PATH/headword_MUST_NOT_DISPLAY"
                    ),
                ), patch.object(
                    module.messagebox, "showerror",
                    side_effect=lambda title, message, **_kw:
                    ordinary_close_alerts.append((title, message)),
                ):
                    review._close_review()
                check(
                    review.winfo_exists()
                    and len(ordinary_close_alerts) == 1
                    and "保存失败" in app.status_var.get()
                    and "PRIVATE_" not in app.status_var.get()
                    + str(ordinary_close_alerts),
                    "native ordinary review close leaked source exception or destroyed UI",
                )
            finally:
                review._filter_rows_active = True

            # When a source-attested focused worker returns no commit and no
            # conflict, its returned edits are unconfirmed: the close request
            # must be disarmed, with all unsaved words retained on screen.
            before_close = pdic_path(page1).read_bytes()
            close_unconfirmed = []
            with patch.object(
                module, "_apply_focused_review_page_updates",
                return_value=([], []),
            ), patch.object(
                module.messagebox, "showerror",
                side_effect=lambda title, message, **_kw:
                close_unconfirmed.append((title, message)),
            ):
                review.filter_vars[0].set("synthetic-close-unconfirmed")
                review._close_review()
                check(
                    review._filter_save_running
                    and review._filter_close_after_save
                    and review.winfo_exists(),
                    "native focused close did not wait on in-flight writer",
                )
                _pump_until(
                    app,
                    lambda: (
                        not review._filter_save_running
                        and not review._filter_close_after_save
                        and review._filter_pending_changes.get(0, {}).get(
                            (80, 76), {}
                        ).get("new_word") == "synthetic-close-unconfirmed"
                        and review.winfo_exists()
                    ),
                    seconds=35,
                    description="G3 native close disarmed after unconfirmed save",
                )
            check(
                review.winfo_exists()
                and pdic_path(page1).read_bytes() == before_close
                and not close_unconfirmed
                and review._filter_pending_changes[0][(80, 76)]["new_word"]
                == "synthetic-close-unconfirmed",
                "native close lost unconfirmed human edit or wrote PDIC",
            )

            # A real background save held before publication may be followed
            # by a close click and an external SECTION drift. The close must
            # NOT destroy the visible editor after failed source verification.
            close_start = threading.Event()
            close_release = threading.Event()
            def gated_close_writer(the_page, pages, index, changes):
                close_start.set()
                if not close_release.wait(timeout=30):
                    raise RuntimeError("synthetic close gate timed out")
                return real_writer(the_page, pages, index, changes)
            close_failed_alerts = []
            try:
                with patch.object(
                    module, "_apply_focused_review_page_updates",
                    side_effect=gated_close_writer,
                ), patch.object(
                    module.messagebox, "showerror",
                    side_effect=lambda title, message, **_kw:
                    close_failed_alerts.append((title, message)),
                ):
                    review.filter_vars[0].set("synthetic-close-source-denied")
                    _pump_until(
                        app,
                        lambda: close_start.is_set()
                        and review._filter_save_running,
                        seconds=35,
                        description="G3 real Tk close writer held before publication",
                    )
                    review._close_review()
                    check(
                        review._filter_close_after_save
                        and review.winfo_exists(),
                        "native close failed to wait for active focused save",
                    )
                    section_path.parent.mkdir(parents=True, exist_ok=True)
                    section_path.write_bytes(
                        b'{"synthetic_close_drift":true}'
                        if section_original is None
                        else section_original + b" "
                    )
                    close_release.set()
                    _pump_until(
                        app,
                        lambda: (
                            not review._filter_save_running
                            and not review._filter_close_after_save
                            and len(close_failed_alerts) == 1
                            and bool(review._filter_pending_changes.get(0))
                            and review.winfo_exists()
                        ),
                        seconds=35,
                        description="G3 native source-drift close refusal",
                    )
                    check(
                        review.winfo_exists()
                        and pdic_path(page1).read_bytes() == before_close
                        and review._filter_pending_changes[0][(80, 76)][
                            "new_word"
                        ] == "synthetic-close-source-denied"
                        and "synthetic-close-source-denied" not in str(
                            close_failed_alerts
                        ),
                        "native failed-close dropped work, leaked word, or published PDIC",
                    )
            finally:
                close_release.set()
                if section_original is None:
                    section_path.unlink(missing_ok=True)
                else:
                    section_path.write_bytes(section_original)

            # A native ReviewWindow synchronous dispatch failure occurs
            # *before* any worker can certify disk state. The user must not
            # lose the StringVar correction, leak the injected private path,
            # or inherit an automatic-close request from the old attempt.
            dispatch_denied_alerts = []
            review.filter_vars[0].set("synthetic-close-dispatch-refused")
            attempted = review._filter_pending_changes.get(0, {}).get((80, 76))
            check(
                attempted is not None
                and attempted["new_word"] == "synthetic-close-dispatch-refused"
                and attempted.get("_focused_save_source_witness")
                == target.get("_focused_save_source_witness"),
                "native dispatch test lacks a source-attested pending editor",
            )
            dispatch_baseline = pdic_path(page1).read_bytes()
            # A scheduler may call done/failed re-entrantly, then reject
            # the launch. The ReviewWindow must not consume that result as
            # confirmed, close early, or produce two Tk error dialogs.
            for early_kind in ("done", "failed"):
                dispatch_denied_alerts.clear()

                def rejected_after_inline_callback(_name, _work, done, failed, **_kw):
                    if early_kind == "done":
                        done(([(0, 80, 76, "synthetic-close-dispatch-refused")], []))
                    else:
                        failed(
                            OSError("PRIVATE_NATIVE_INLINE_CALLBACK_PATH/word"),
                            "PRIVATE_NATIVE_INLINE_CALLBACK_TRACE",
                        )
                    raise OSError("PRIVATE_NATIVE_DISPATCH_PATH/word")

                with patch.object(
                    app, "_start_ui_worker",
                    side_effect=rejected_after_inline_callback,
                ), patch.object(
                    module.messagebox, "showerror",
                    side_effect=lambda title, msg, **_kw:
                    dispatch_denied_alerts.append((title, msg)),
                ):
                    review._close_review()
                check(
                    review.winfo_exists()
                    and review.filter_vars[0].get() == "synthetic-close-dispatch-refused"
                    and target["original_word"] == "synthetic-native-retried"
                    and review._filter_pending_changes.get(0, {}).get(
                        (80, 76), {}
                    ).get("new_word") == "synthetic-close-dispatch-refused"
                    and review._filter_save_launch_failed
                    and not review._filter_save_running
                    and not review._filter_close_after_save
                    and pdic_path(page1).read_bytes() == dispatch_baseline
                    and len(dispatch_denied_alerts) == 1
                    and "PRIVATE_" not in str(dispatch_denied_alerts)
                    + app.status_var.get(),
                    "native inline callback after rejected launch lost the human edit, "
                    "claimed success, leaked source or closed the ReviewWindow",
                )

            # A new explicit close attempt after restoring the original
            # source really saves one word then destroys the ReviewWindow.
            review.filter_vars[0].set("synthetic-close-committed")
            review._close_review()
            check(
                review._filter_close_after_save
                and review._filter_save_running,
                "native positive close was not tied to the actual save worker",
            )
            # Window destruction alone is not a physical-save oracle:
            # unrelated main-app autosave/editor reconciliation may still
            # be draining on the Tk event loop. Require five consecutive
            # event pumps with *all* authoritative disk/source/Tk checks,
            # not a transient status message or just an empty worker queue.
            def final_source_checks():
                try:
                    final_fields = [
                        line.split("#")
                        for line in pdic_path(page1).read_text(
                            encoding="utf-8"
                        ).splitlines()
                        if line.strip()
                    ]
                    return {
                        "pdic_row_count": len(final_fields) == 2,
                        "pdic_word": len(final_fields) >= 1
                        and final_fields[0][0] == "synthetic-close-committed",
                        "pdic_other_fields": len(final_fields) >= 1
                        and final_fields[0][1:] == before_drift_rows[0][1:],
                        "pdic_other_row": len(final_fields) >= 2
                        and final_fields[1] == before_drift_rows[1],
                        "main_entries": [(e.word, e.x, e.y) for e in app.entries]
                        == [("synthetic-close-committed", 80, 76),
                            ("synthetic-beta", 85, 182)],
                        "ppp": ppp_read_path_for_image(page1).read_bytes() == before_ppp,
                        "settings": settings_path(root).read_bytes() == before_settings,
                        "section": (section_path.read_bytes()
                                    if section_original is not None else None)
                        == section_original,
                        "images": [p.read_bytes() for p in (page1, page2)] == before_image,
                        "no_ocr_origin": not origin.exists(),
                    }
                except (OSError, UnicodeError):
                    # A transient file read during a concurrent save is not
                    # proof of success; retry until stable or fail on timeout.
                    return {"source_readable": False}

            consecutive_complete = [0]
            def verified_close_stable():
                if (review.winfo_exists()
                        or app.review_window is not None
                        or not all(final_source_checks().values())):
                    consecutive_complete[0] = 0
                    return False
                consecutive_complete[0] += 1
                return consecutive_complete[0] >= 5

            _pump_until(
                app,
                verified_close_stable,
                seconds=35,
                description="G3 native close and five stable source-owned PDIC/Tk observations",
            )
            final_checks = final_source_checks()
            check(
                all(final_checks.values()),
                "native successful focused close source ownership mismatch: "
                + ", ".join(k for k, ok in final_checks.items() if not ok),
            )
            print(
                "G3 R4.2 native Tk close redaction + pending refusal"
                " + source-drift refusal + verified close: OK",
                flush=True,
            )
        finally:
            if review is not None and review.winfo_exists():
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
