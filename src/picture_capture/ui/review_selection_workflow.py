"""Physical owner of PictureCaptureApp OCR review selection and persisted evidence.

Native Tk callbacks remain in app.py as thin delegates.  All external GUI and IO
bindings are captured afresh by a frozen per-call dependency snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from pathlib import Path
    from ..models import Entry as WordEntry


@dataclass(frozen=True)
class ReviewSelectionDeps:
    tk: object
    json: object
    replace: object
    WordEntry: object
    ocr_cache_root: object
    read_pdic: object
    pdic_path: object
    _review_crop_settings: object
    _review_line_box: object
    OCRConflictReviewDialog: object


def _paddle_cache_path(self, deps: ReviewSelectionDeps) -> Path | None:
    ocr_cache_root = deps.ocr_cache_root
    if not self.project or not self.current_page:
        return None
    return ocr_cache_root(self.project.root) / f"{self.current_page.stem}.json"

def _manual_selection_path(self, deps: ReviewSelectionDeps) -> Path | None:
    cache = self._paddle_cache_path()
    return cache.with_name(f"{cache.stem}_manual_selection.json") if cache else None

def _read_manual_overrides(self, deps: ReviewSelectionDeps) -> dict:
    json = deps.json
    path = self._manual_selection_path()
    if (
        path is not None
        and self._pending_manual_override_path == path
        and self._pending_manual_override_payload is not None
    ):
        return self._pending_manual_override_payload
    if not path or not path.exists():
        return {"version": 1, "overrides": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError
        raw.setdefault("version", 1)
        raw.setdefault("overrides", {})
        return raw
    except Exception:
        return {"version": 1, "overrides": {}}

def _flush_pending_manual_override(self, deps: ReviewSelectionDeps) -> None:
    json = deps.json
    path = self.__dict__.get("_pending_manual_override_path")
    payload = self.__dict__.get("_pending_manual_override_payload")
    if path is None or payload is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    self._pending_manual_override_path = None
    self._pending_manual_override_payload = None

def _write_manual_override(
    self, deps: ReviewSelectionDeps, cand: dict, *, selected: bool, word: str | None = None,
    engine: str | None = None, defer: bool = False,
) -> None:
    json = deps.json
    path = self._manual_selection_path()
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # If another page somehow still has a queued sidecar write, commit it
    # before switching the in-memory payload. Normal navigation already
    # force-flushes, but this guard prevents cross-page contamination.
    if self._pending_manual_override_path not in {None, path}:
        self._flush_pending_manual_override()
    payload = self._read_manual_overrides()
    cid = str(cand.get("candidate_id", ""))
    if not cid:
        return
    payload["page"] = self.current_page.stem if self.current_page else ""
    payload["overrides"][cid] = {
        "selected": bool(selected),
        "word": str(word if word is not None else cand.get("word", "")),
        "engine": str(engine if engine is not None else cand.get("final_engine", "manual")),
    }
    if defer:
        self._pending_manual_override_path = path
        self._pending_manual_override_payload = payload
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if self._pending_manual_override_path == path:
            self._pending_manual_override_path = None
            self._pending_manual_override_payload = None

def _queue_proofreading_add_evidence(self, deps: ReviewSelectionDeps, x: int, y: int) -> None:
    """Stage a user canvas click, NOT a durable event until PDIC commits."""
    read_pdic = deps.read_pdic
    pdic_path = deps.pdic_path
    if not getattr(getattr(self, "settings", None), "proofreading_event_capture", False):
        return
    state = self.__dict__
    if "_pending_evidence_add" in state:
        # More than one insertion or additional save requests coalesced.
        state["_pending_evidence_add"] = False
        return
    project = getattr(self, "project", None)
    page = getattr(self, "current_page", None)
    if project is None or page is None:
        return
    try:
        old = read_pdic(pdic_path(page))
    except (OSError, ValueError):
        return
    from ..proofreading.capture import verified_ocr_preedit_fingerprints
    cache_fn = getattr(self, "_paddle_cache_path", None)
    cache = cache_fn() if callable(cache_fn) else None
    source = verified_ocr_preedit_fingerprints(cache, pdic_path(page))
    state["_pending_evidence_add"] = (page, old, (int(x), int(y)), source)

def _flush_proofreading_add_evidence(self, deps: ReviewSelectionDeps) -> None:
    """Record the manual click only after a successfully saved PDIC."""
    snapshot = self.__dict__.pop("_pending_evidence_add", None)
    if not isinstance(snapshot, tuple):
        return
    if not getattr(getattr(self, "settings", None), "proofreading_event_capture", False):
        return
    if len(snapshot) != 4:
        return
    page, old, xy, source = snapshot
    project = getattr(self, "project", None)
    if project is None or getattr(self, "current_page", None) != page:
        return
    try:
        from ..proofreading.capture import capture_saved_manual_addition
        capture_saved_manual_addition(
            project_root=project.root, page=page,
            prior_pdic_entries=old, expected_xy=xy,
            source_fingerprints=source,
        )
    except (OSError, ValueError, TypeError):
        status = getattr(self, "status_var", None)
        if status is not None:
            status.set("词条已保存，但本地新增词条日志写入失败。")

def _queue_proofreading_candidate_evidence(self, deps: ReviewSelectionDeps, cand: dict, selected: bool) -> None:
    """Keep one pre-save checkbox snapshot; coalesced edits are ambiguous."""
    read_pdic = deps.read_pdic
    pdic_path = deps.pdic_path
    state = self.__dict__
    if not getattr(getattr(self, "settings", None), "proofreading_event_capture", False):
        return
    if "_pending_evidence_toggle" in state:
        state["_pending_evidence_toggle"] = False
        return
    page = getattr(self, "current_page", None)
    if page is None or getattr(self, "project", None) is None:
        return
    candidate_id = str(cand.get("candidate_id", "") or "")
    if not candidate_id or sum(
        str(row.get("candidate_id", "")) == candidate_id
        for row in getattr(self, "ocr_review_candidates", ())
        if isinstance(row, dict)
    ) != 1:
        return
    try:
        before = read_pdic(pdic_path(page))
        override = self._manual_selection_path()
        expected = (
            str(cand.get("word", "")),
            int(cand.get("source_x", 0)), int(cand.get("source_y", 0)),
        )
    except (OSError, ValueError, TypeError):
        return
    if override is None:
        return
    position_switch = None
    group_id = str(cand.get("position_group_id") or "")
    if selected and group_id:
        siblings = [
            row for row in getattr(self, "ocr_review_candidates", ())
            if row is not cand and isinstance(row, dict)
            and row.get("position_group_id") == group_id
            and str(row.get("candidate_id") or "") != candidate_id
        ]
        # Only an actual selected, uniquely linked sibling counts as the
        # pre-click physical-headword location; never infer from nearest Y.
        matched = [
            (str(entry.candidate_id), (str(entry.word), int(entry.x), int(entry.y)))
            for sibling in siblings
            for entry in getattr(self, "entries", ())
            if str(entry.candidate_id or "") == str(sibling.get("candidate_id") or "")
            and str(entry.candidate_id or "")
        ]
        if len(matched) == 1:
            removed_id, removed_row = matched[0]
            if sum(
                str(row.get("candidate_id") or "") == removed_id
                for row in getattr(self, "ocr_review_candidates", ())
                if isinstance(row, dict)
            ) == 1:
                position_switch = (removed_id, removed_row, group_id)
    from ..proofreading.capture import verified_ocr_preedit_fingerprints
    cache_fn = getattr(self, "_paddle_cache_path", None)
    cache = cache_fn() if callable(cache_fn) else None
    source = verified_ocr_preedit_fingerprints(cache, pdic_path(page))
    state["_pending_evidence_toggle"] = (
        page, before, expected, candidate_id, bool(selected), override,
        position_switch, source,
    )

def _flush_proofreading_candidate_evidence(self, deps: ReviewSelectionDeps) -> None:
    """Only after PDIC and delayed manual-selection sidecar are both saved."""
    snapshot = self.__dict__.pop("_pending_evidence_toggle", None)
    if not isinstance(snapshot, tuple):
        return
    if len(snapshot) != 8:
        return
    page, before, expected, candidate_id, selected, override, position_switch, source = snapshot
    if not getattr(getattr(self, "settings", None), "proofreading_event_capture", False):
        return
    project = getattr(self, "project", None)
    # A deferred callback must never attribute a previous page's click
    # after navigation has already changed the active page.
    if project is None or getattr(self, "current_page", None) != page:
        return
    try:
        from ..proofreading.capture import (
            capture_saved_candidate_selection,
            capture_saved_position_switch,
        )
        recorded = capture_saved_candidate_selection(
            project_root=project.root, page=page,
            prior_pdic_entries=before, expected_entry=expected,
            candidate_id=candidate_id, candidate_id_unique=True,
            selected=selected, manual_selection_path=override,
            source_fingerprints=source,
        )
        if not recorded and selected and position_switch is not None:
            old_candidate_id, old_entry, group_id = position_switch
            capture_saved_position_switch(
                project_root=project.root, page=page,
                prior_pdic_entries=before,
                removed_entry=old_entry, added_entry=expected,
                removed_candidate_id=old_candidate_id,
                added_candidate_id=candidate_id,
                position_group_id=group_id,
                manual_selection_path=override,
                source_fingerprints=source,
            )
    except (OSError, ValueError, TypeError):
        # Journal failure must not roll back user PDIC or overrides.
        status = getattr(self, "status_var", None)
        if status is not None:
            status.set("候选选择已保存，但本地校对日志写入失败。")

def _schedule_deferred_page_save(self, deps: ReviewSelectionDeps, *, sync_editors: bool = True) -> None:
    """Coalesce rapid checkbox edits while preserving an exact page snapshot."""
    replace = deps.replace
    tk = deps.tk
    project = self.__dict__.get("project")
    current_page = self.__dict__.get("current_page")
    image = self.__dict__.get("image")
    if not project or not current_page or image is None:
        return
    # Editor contents belong to the same in-memory page model and must be in
    # the snapshot; otherwise a checkbox click could save stale text. The
    # checkbox path has already synchronized them once, so it can skip the
    # duplicate widget walk here.
    if sync_editors:
        self._sync_entry_editor_texts()
    snapshot = (
        current_page,
        [replace(entry) for entry in self.entries],
        int(image.width),
        self.pages_tuple(),
        int(self.current_index),
    )
    self._deferred_save_page = current_page
    self._deferred_save_snapshot = snapshot
    deferred_job = self.__dict__.get("_deferred_save_job")
    if deferred_job is not None:
        try:
            self.after_cancel(deferred_job)
        except tk.TclError:
            pass
    self._deferred_save_job = self.after(self._deferred_save_delay_ms, self._flush_deferred_page_save)

def set_candidate_selected(self, deps: ReviewSelectionDeps, cand: dict, selected: bool) -> bool:
    WordEntry = deps.WordEntry
    if not self._claim_page_for_manual_edit():
        return False
    self._queue_proofreading_candidate_evidence(cand, selected)
    # Commit every visible editor by object identity before changing the
    # entries list. This prevents a middle-row removal from reassigning the
    # following editor texts to earlier entries.
    self._sync_entry_editor_texts()
    removed_entries: list[WordEntry] = []
    added_entries: list[WordEntry] = []

    # Refined-Y and original/anchor-Y fallback rows are two positions for
    # the same physical headword. Selecting either is a one-click switch.
    group_id = str(cand.get("position_group_id", ""))
    if selected and group_id:
        for sibling in self.ocr_review_candidates:
            if sibling is cand or str(sibling.get("position_group_id", "")) != group_id:
                continue
            sibling_entry = self._entry_for_candidate(sibling)
            if sibling_entry is not None and sibling_entry in self.entries:
                self.entries.remove(sibling_entry)
                removed_entries.append(sibling_entry)
            sibling["selected"] = False
            sibling_var = self.candidate_check_vars.get(str(sibling.get("candidate_id", "")))
            if sibling_var is not None:
                sibling_var.set(False)
            self._write_manual_override(
                sibling, selected=False,
                word=str(sibling.get("word", "")), engine="position_switch", defer=True,
            )

    entry = self._entry_for_candidate(cand)
    if selected:
        if entry is None:
            entry = WordEntry(
                str(cand.get("word", "")), int(cand.get("source_x", 0)), int(cand.get("source_y", 0)),
                confidence=(float(cand.get("confidence")) if cand.get("confidence") is not None else None),
                ocr_source=str(cand.get("final_engine", "manual")),
                alphabetical_warning=str(cand.get("alphabetical_warning", "")),
                candidate_id=str(cand.get("candidate_id", "")),
                final_engine=str(cand.get("final_engine", "")),
                issue_type=",".join(str(x) for x in cand.get("issue_types", []) or []),
                parser_score=(float(cand.get("score")) if cand.get("score") is not None else None),
                manually_selected=True,
            )
            self.entries.append(entry)
            added_entries.append(entry)
        cand["selected"] = True
    else:
        if entry is not None and entry in self.entries:
            self.entries.remove(entry)
            removed_entries.append(entry)
        cand["selected"] = False
    self._sort_entries_reading_order()
    self._write_manual_override(
        cand, selected=selected,
        word=(entry.word if entry else str(cand.get("word", ""))),
        engine="manual_checkbox", defer=True,
    )
    target_var = self.candidate_check_vars.get(str(cand.get("candidate_id", "")))
    if target_var is not None:
        target_var.set(bool(selected))

    # The data model is already final at this point. Only the affected entry
    # overlay is changed; the cached background and unrelated editors stay
    # untouched. Disk I/O is coalesced below.
    self._update_entry_overlays_local(removed=removed_entries, added=added_entries)
    self._schedule_deferred_page_save(sync_editors=False)
    variant = str(cand.get("position_variant", "refined"))
    if selected and variant in {"original", "anchor"}:
        self.status_var.set("已切回原始 Y / 图像锚点 Y")
    elif selected and variant == "refined":
        self.status_var.set("已使用精修 Y")
    return True

def apply_candidate_choice(self, deps: ReviewSelectionDeps, cand: dict, engine: str, word: str) -> None:
    WordEntry = deps.WordEntry
    if not self._claim_page_for_manual_edit():
        return
    self._sync_entry_editor_texts()
    side = cand.get(engine, {}) if engine in {"paddle", "tesseract", "lens"} else {}
    if engine in {"paddle", "tesseract", "lens"} and side:
        if side.get("y") is not None: cand["source_y"] = int(side.get("y"))
        if side.get("confidence") is not None: cand["confidence"] = float(side.get("confidence"))
        if side.get("score") is not None: cand["score"] = float(side.get("score"))
    cand["word"] = word
    cand["final_engine"] = engine
    cand["selected"] = True
    cand["decision_reason"] = "manual_review_choice"
    issues = list(cand.get("issue_types", []) or [])
    if "MANUAL_OVERRIDE" not in issues: issues.append("MANUAL_OVERRIDE")
    cand["issue_types"] = issues
    old = self._entry_for_candidate(cand)
    if old is not None: self.entries.remove(old)
    entry = WordEntry(
        word, int(cand.get("source_x", 0)), int(cand.get("source_y", 0)),
        confidence=(float(cand.get("confidence")) if cand.get("confidence") is not None else None),
        ocr_source=engine, candidate_id=str(cand.get("candidate_id", "")), final_engine=engine,
        issue_type=",".join(issues), parser_score=(float(cand.get("score")) if cand.get("score") is not None else None),
        manually_selected=True,
    )
    self.entries.append(entry); self._sort_entries_reading_order()
    self._write_manual_override(cand, selected=True, word=word, engine=engine)
    self.save_pdic(silent=True); self.redraw()

def candidate_checkbox_changed(self, deps: ReviewSelectionDeps, candidate_id: str, var: tk.BooleanVar) -> None:
    cand = self.get_review_candidate(candidate_id)
    if cand is not None:
        requested = bool(var.get())
        if not self.set_candidate_selected(cand, requested):
            # The checkbox toggles before the command callback fires. If a
            # background worker currently owns the page, immediately restore
            # the visual state so UI and in-memory data cannot diverge.
            var.set(self._candidate_is_selected(cand))

def _scroll_review_entry_into_view(self, deps: ReviewSelectionDeps, entry: WordEntry) -> None:
    """Scroll the main image only if the proofreading row is off-screen."""
    tk = deps.tk
    _review_crop_settings = deps._review_crop_settings
    _review_line_box = deps._review_line_box
    if self.image is None:
        return
    try:
        geometry = self._get_cached_display_geometry()
        crop_settings = _review_crop_settings(
            self.image, self.settings, self.canvas.winfo_width()
        )
        left, top, right, bottom = _review_line_box(
            entry, geometry, self.image, crop_settings
        )
        scale = self.view_scale
        left, top, right, bottom = (
            left * scale, top * scale, right * scale, bottom * scale
        )
        canvas = self.canvas
        canvas.update_idletasks()
        viewport_w = max(1, canvas.winfo_width())
        viewport_h = max(1, canvas.winfo_height())
        current_x = canvas.canvasx(0)
        current_y = canvas.canvasy(0)
        pad = 16
        new_x = current_x
        new_y = current_y
        if left < current_x + pad or right > current_x + viewport_w - pad:
            new_x = max(0.0, left - pad)
        if top < current_y + pad or bottom > current_y + viewport_h - pad:
            new_y = max(0.0, top - pad)
        image_w = max(1.0, self.image.width * scale)
        image_h = max(1.0, self.image.height * scale)
        if new_x != current_x:
            max_x = max(0.0, image_w - viewport_w)
            canvas.xview_moveto(min(new_x, max_x) / image_w)
        if new_y != current_y:
            max_y = max(0.0, image_h - viewport_h)
            canvas.yview_moveto(min(new_y, max_y) / image_h)
    except (tk.TclError, ValueError, TypeError, AttributeError):
        return

def open_ocr_conflict_review(self, deps: ReviewSelectionDeps) -> None:
    OCRConflictReviewDialog = deps.OCRConflictReviewDialog
    if not self.guard(): return
    self._load_ocr_review_candidates()
    if self.ocr_review_window is not None and self.ocr_review_window.winfo_exists():
        self.ocr_review_window.refresh(); self.ocr_review_window.lift(); return
    self.ocr_review_window = OCRConflictReviewDialog(self)

def _current_page_quality_text(self, deps: ReviewSelectionDeps) -> str:
    json = deps.json
    path = self._paddle_cache_path()
    if not path or not path.exists(): return ""
    try:
        q = json.loads(path.read_text(encoding="utf-8")).get("page_quality", {}) or {}
        if "agreement" not in q: return ""
        return f"双OCR一致性 {float(q['agreement'])*100:.1f}% / 待复核 {int(q.get('needs_review',0))}"
    except Exception:
        return ""

def _restore_entry_ocr_metadata(self, deps: ReviewSelectionDeps, payload: dict | None = None) -> None:
    """Restore runtime confidence/source/warnings from the Paddle JSON sidecar."""
    ocr_cache_root = deps.ocr_cache_root
    json = deps.json
    if not self.project or not self.current_page or not self.entries:
        return
    if payload is None:
        path = ocr_cache_root(self.project.root) / f"{self.current_page.stem}.json"
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
    try:
        meta = list(payload.get("final_entries") or [])
        # Review candidates may have been manually toggled after the last OCR
        # cache write; use them as metadata fallback for PDIC rows.
        for cand in payload.get("review_candidates") or []:
            if not isinstance(cand, dict):
                continue
            meta.append({
                "word": cand.get("word", ""), "x": cand.get("source_x", 0), "y": cand.get("source_y", 0),
                "confidence": cand.get("confidence"), "ocr_source": cand.get("final_engine", ""),
                "alphabetical_warning": cand.get("alphabetical_warning", ""),
                "candidate_id": cand.get("candidate_id", ""), "final_engine": cand.get("final_engine", ""),
                "issue_type": ",".join(cand.get("issue_types", []) or []), "parser_score": cand.get("score"),
            })
    except Exception:
        return
    if not meta:
        return
    used: set[int] = set()
    for entry in self.entries:
        best = None
        best_distance = None
        for i, item in enumerate(meta):
            if i in used:
                continue
            try:
                x = int(item.get("x", entry.x)); y = int(item.get("y", entry.y))
            except (TypeError, ValueError):
                continue
            if abs(x - entry.x) > 12:
                continue
            word = str(item.get("word", ""))
            word_penalty = 0 if not entry.word or not word or entry.word.casefold() == word.casefold() else 12
            distance = abs(y - entry.y) + word_penalty
            if distance <= 18 and (best_distance is None or distance < best_distance):
                best = (i, item); best_distance = distance
        if best is None:
            continue
        i, item = best; used.add(i)
        value = item.get("confidence")
        try:
            entry.confidence = float(value) if value is not None else None
        except (TypeError, ValueError):
            entry.confidence = None
        entry.ocr_source = str(item.get("ocr_source", ""))
        entry.alphabetical_warning = str(item.get("alphabetical_warning", ""))
        entry.candidate_id = str(item.get("candidate_id", ""))
        entry.final_engine = str(item.get("final_engine", item.get("ocr_source", "")))
        entry.issue_type = str(item.get("issue_type", ""))
        try:
            entry.parser_score = float(item.get("parser_score")) if item.get("parser_score") is not None else None
        except (TypeError, ValueError):
            entry.parser_score = None
        entry.manually_selected = bool(item.get("manually_selected", False))

