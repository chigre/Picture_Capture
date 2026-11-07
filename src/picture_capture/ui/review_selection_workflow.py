"""Physical owner of PictureCaptureApp OCR review selection and persisted evidence.

Native Tk callbacks remain in app.py as thin delegates.  All external GUI and IO
bindings are captured afresh by a frozen per-call dependency snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from copy import deepcopy
from pathlib import Path

from ..proofreading.candidate_delete import _load_unambiguous_json
from ..proofreading.transactions import _atomic_bytes, _bytes_or_absent

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

def _validated_manual_selection(path: Path, stem: str) -> tuple[bytes | None, dict]:
    """A display fallback must never authorize wiping human selection bytes."""
    source = _bytes_or_absent(path)
    if source is None:
        return None, {"version": 1, "overrides": {}}
    try:
        document = _load_unambiguous_json(source)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise RuntimeError("R3 人工候选选择文件损坏或含歧义字段，拒绝覆盖") from exc
    if (
        not isinstance(document, dict)
        or type(document.get("version", 1)) is not int
        or document.get("version", 1) != 1
        or ("page" in document and document["page"] != stem)
        or not isinstance(document.get("overrides"), dict)
    ):
        raise RuntimeError("R3 人工候选选择格式或页归属不可信，拒绝覆盖")
    document.setdefault("version", 1)
    return source, document


def _manual_override_preflight(self, cand: dict | None = None) -> bool:
    """Validate persisted/pending human decisions before checkbox model edits."""
    path_fn = getattr(self, "_manual_selection_path", None)
    if not callable(path_fn):
        # Existing isolated UI tests can exercise model logic with a mocked
        # writer; production must always provide the real path binding.
        return True
    path = path_fn()
    if path is None:
        return False
    if self.__dict__.get("_pending_manual_override_path") not in (None, path):
        self._flush_pending_manual_override()
    source, payload = _validated_manual_selection(path, self.current_page.stem)
    if self.__dict__.get("_pending_manual_override_path") == path:
        original = self.__dict__.get("_pending_manual_override_origin")
        if original != (path.resolve(), source):
            raise RuntimeError("R3 延迟候选人工决策的原始来源已变化，拒绝覆盖")
        payload = self.__dict__["_pending_manual_override_payload"]
        if not isinstance(payload, dict):
            raise RuntimeError("R3 延迟候选人工决策内容不可信")
    if cand:
        prior = payload["overrides"].get(str(cand.get("candidate_id") or ""))
        if prior is not None and (
            not isinstance(prior, dict)
            or set(prior) - {"selected", "word", "engine"}
            or ("word" in prior and prior["word"] != str(cand.get("word", "")))
        ):
            raise RuntimeError("R3 该候选有未知人工扩展字段或来源词不一致，拒绝覆盖")
    return True


def _read_manual_overrides(self, deps: ReviewSelectionDeps) -> dict:
    path = self._manual_selection_path()
    if path is None:
        return {"version": 1, "overrides": {}}
    source, payload = _validated_manual_selection(path, self.current_page.stem)
    if (self.__dict__.get("_pending_manual_override_path") == path
            and self.__dict__.get("_pending_manual_override_payload") is not None):
        if self.__dict__.get("_pending_manual_override_origin") != (
            path.resolve(), source,
        ):
            raise RuntimeError("R3 延迟候选人工决策来源已被其他人修改")
        return deepcopy(self._pending_manual_override_payload)
    return payload


def verify_pending_manual_source(self, page_stem: str) -> None:
    """Read-only preflight before *any* PDIC publication paired with a manual edit.

    Do not clear pending edits on failure. This is an optimistic source guard,
    not a cross-file CAS; races after the check must still be quarantined.
    """
    state = self.__dict__
    path = state.get("_pending_manual_override_path")
    payload = state.get("_pending_manual_override_payload")
    origin = state.get("_pending_manual_override_origin")
    if path is None and payload is None and origin is None:
        return
    if (
        not isinstance(path, Path)
        or not isinstance(payload, dict)
        or payload.get("page") != page_stem
        or not isinstance(origin, tuple) or len(origin) != 2
        or origin[0] != path.resolve()
    ):
        raise RuntimeError("R3 延迟人工选择页归属或来源锁定不可信，拒绝 PDIC 保存")
    raw, _ = _validated_manual_selection(path, page_stem)
    if raw != origin[1] or _bytes_or_absent(path) != origin[1]:
        raise RuntimeError("R3 人工选择来源已被其他人修改，拒绝 PDIC 保存")


def _flush_pending_manual_override(self, deps: ReviewSelectionDeps) -> None:
    path = self.__dict__.get("_pending_manual_override_path")
    payload = self.__dict__.get("_pending_manual_override_payload")
    if path is None or payload is None:
        return
    verify_pending_manual_source(self, str(payload.get("page", "")))
    source_pin = self.__dict__["_pending_manual_override_origin"]
    # A same-file atomic replace avoids truncating the original on I/O
    # failure. Byte preflight is optimistic, NOT an OS atomic compare-and-swap.
    encoded = deps.json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    if _bytes_or_absent(path) != source_pin[1]:
        raise RuntimeError("R3 写入前人工候选来源变化，拒绝覆盖")
    _atomic_bytes(path, encoded)
    self._pending_manual_override_path = None
    self._pending_manual_override_payload = None
    self.__dict__.pop("_pending_manual_override_origin", None)


def _write_manual_override(
    self, deps: ReviewSelectionDeps, cand: dict, *, selected: bool, word: str | None = None,
    engine: str | None = None, defer: bool = False,
) -> None:
    path = self._manual_selection_path()
    if not path:
        raise RuntimeError("R3 无人工候选选择路径，拒绝写入")
    if self.__dict__.get("_pending_manual_override_path") not in (None, path):
        self._flush_pending_manual_override()
    _manual_override_preflight(self, cand)
    source, _ = _validated_manual_selection(path, self.current_page.stem)
    payload = self._read_manual_overrides()
    cid = str(cand.get("candidate_id", ""))
    if not cid:
        raise RuntimeError("R3 候选没有唯一 ID，拒绝人工选择落盘")
    payload["page"] = self.current_page.stem
    payload["overrides"][cid] = {
        "selected": bool(selected),
        "word": str(word if word is not None else cand.get("word", "")),
        "engine": str(engine if engine is not None else cand.get("final_engine", "manual")),
    }
    if defer:
        self._pending_manual_override_path = path
        self._pending_manual_override_payload = payload
        self.__dict__["_pending_manual_override_origin"] = (path.resolve(), source)
    else:
        # No deferred source pin: revalidate in case another proofreader wrote
        # while the UI was preparing the candidate payload.
        if _bytes_or_absent(path) != source:
            raise RuntimeError("R3 人工候选选择来源已变化，拒绝覆盖")
        _atomic_bytes(
            path, deps.json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        if self.__dict__.get("_pending_manual_override_path") == path:
            self._pending_manual_override_path = None
            self._pending_manual_override_payload = None
            self.__dict__.pop("_pending_manual_override_origin", None)

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
    old_snapshot = self.__dict__.get("_deferred_save_snapshot")
    old_pin = self.__dict__.get("_deferred_save_pdic_origin")
    if old_snapshot is not None:
        if (
            old_snapshot[0] != current_page
            or not isinstance(old_pin, tuple) or len(old_pin) != 2
            or old_pin[0] != current_page
        ):
            raise RuntimeError("R3 旧页延迟 PDIC 来源未完成，拒绝改写新页")
        source_pin = old_pin
    else:
        # Freeze the *first* checkbox's PDIC bytes. Coalesced same-page
        # clicks must never refresh the pin to an intervening writer's file.
        source_pin = (current_page, _bytes_or_absent(deps.pdic_path(current_page)))
    snapshot = (
        current_page,
        [replace(entry) for entry in self.entries],
        int(image.width),
        self.pages_tuple(),
        int(self.current_index),
    )
    self._deferred_save_page = current_page
    self._deferred_save_snapshot = snapshot
    self._deferred_save_pdic_origin = source_pin
    deferred_job = self.__dict__.get("_deferred_save_job")
    if deferred_job is not None:
        try:
            self.after_cancel(deferred_job)
        except tk.TclError:
            pass
    self._deferred_save_job = self.after(self._deferred_save_delay_ms, self._flush_deferred_page_save)

_PENDING_MANUAL_KEYS = (
    "_pending_manual_override_path",
    "_pending_manual_override_payload",
    "_pending_manual_override_origin",
)


def _remember_pending_manual(self) -> dict:
    """Retain an in-memory staging snapshot, never copy or rewrite disk bytes."""
    return {
        key: deepcopy(self.__dict__[key])
        for key in _PENDING_MANUAL_KEYS if key in self.__dict__
    }


def _restore_pending_manual(self, previous: dict) -> None:
    for key in _PENDING_MANUAL_KEYS:
        if key in previous:
            self.__dict__[key] = previous[key]
        else:
            self.__dict__.pop(key, None)


def _restore_pending_evidence(self, previous: tuple[bool, object]) -> None:
    present, value = previous
    if present:
        self.__dict__["_pending_evidence_toggle"] = value
    else:
        self.__dict__.pop("_pending_evidence_toggle", None)


def _owned_entry_for_candidate(self, cand: dict):
    """Return only a uniquely candidate_id-owned Entry; never infer via near X/Y.

    Read-only OCR menu lookup permits approximate visual matching, but a
    destructive position switch/choice cannot adopt a neighboring headword.
    """
    cid = str(cand.get("candidate_id") or "")
    if not cid:
        raise RuntimeError("候选缺少可信唯一 ID")
    owners = [
        row for row in self.entries
        if str(getattr(row, "candidate_id", "") or "") == cid
    ]
    if len(owners) != 1 and owners:
        raise RuntimeError("同一候选 ID 关联多条词头，拒绝误归属")
    if owners:
        return owners[0]
    # No verified owner: do not create a second Entry at an occupied
    # coordinate under a different/legacy blank candidate_id.
    try:
        xy = (int(cand.get("source_x", 0)), int(cand.get("source_y", 0)))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("候选缺少可信原图 X/Y") from exc
    if any((int(row.x), int(row.y)) == xy for row in self.entries):
        raise RuntimeError("候选原图坐标已由其他或无主词头占用")
    return None


def set_candidate_selected(self, deps: ReviewSelectionDeps, cand: dict, selected: bool) -> bool:
    WordEntry = deps.WordEntry
    if not self._claim_page_for_manual_edit():
        return False
    if self.__dict__.get("_deferred_save_uncertain", False):
        self.status_var.set("候选未更改：当前页上次保存结果不确定，请先重开核对。")
        return False
    cid = str(cand.get("candidate_id") or "")
    candidates = getattr(self, "ocr_review_candidates", ())
    if (not cid or sum(
            str(row.get("candidate_id") or "") == cid
            for row in candidates if isinstance(row, dict)
        ) != 1):
        self.status_var.set("候选未更改：候选 ID 缺失或归属不唯一。")
        return False
    group = str(cand.get("position_group_id", ""))
    siblings = [
        row for row in candidates
        if selected and group and row is not cand and isinstance(row, dict)
        and str(row.get("position_group_id", "")) == group
    ]
    try:
        if not _manual_override_preflight(self, cand):
            return False
        for sibling in siblings:
            if not _manual_override_preflight(self, sibling):
                return False
        # An already queued checkbox owns the FIRST PDIC version. Failure
        # must occur before changing any Entry, checkbox or candidate flag.
        queued = self.__dict__.get("_deferred_save_snapshot")
        if queued is not None:
            pin = self.__dict__.get("_deferred_save_pdic_origin")
            page = getattr(self, "current_page", None)
            path_fn = getattr(deps, "pdic_path", None)
            if (page is None or not callable(path_fn)
                    or not isinstance(pin, tuple) or len(pin) != 2
                    or pin[0] != page
                    or _bytes_or_absent(path_fn(page)) != pin[1]):
                raise RuntimeError("R3 先前延迟 PDIC 归属已变化")
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        self.status_var.set(f"候选未更改：{exc}")
        return False

    # Retain legacy R2 evidence order: pre-edit snapshot, editor sync, then
    # manual staging. A refusal discards only this attempted evidence.
    evidence_before = (
        "_pending_evidence_toggle" in self.__dict__,
        self.__dict__.get("_pending_evidence_toggle"),
    )
    self._queue_proofreading_candidate_evidence(cand, selected)
    self._sync_entry_editor_texts()
    pending_before = _remember_pending_manual(self)
    try:
        entry = _owned_entry_for_candidate(self, cand)
        planned_entry = entry
        if selected and entry is None:
            # Parse untrusted OCR numeric fields BEFORE staging any sibling
            # override or changing model membership.
            planned_entry = WordEntry(
                str(cand.get("word", "")),
                int(cand.get("source_x", 0)), int(cand.get("source_y", 0)),
                confidence=(float(cand.get("confidence")) if cand.get("confidence") is not None else None),
                ocr_source=str(cand.get("final_engine", "manual")),
                alphabetical_warning=str(cand.get("alphabetical_warning", "")),
                candidate_id=cid,
                final_engine=str(cand.get("final_engine", "")),
                issue_type=",".join(str(x) for x in cand.get("issue_types", []) or []),
                parser_score=(float(cand.get("score")) if cand.get("score") is not None else None),
                manually_selected=True,
            )
        # Every sibling/target decision must stage successfully as one
        # in-memory payload before the first Tk or Entry membership mutation.
        # No manual_selection bytes are published here; the existing paired
        # deferred/regular PDIC writer owns final publication.
        for sibling in siblings:
            self._write_manual_override(
                sibling, selected=False,
                word=str(sibling.get("word", "")),
                engine="position_switch", defer=True,
            )
        self._write_manual_override(
            cand, selected=selected,
            word=(planned_entry.word if planned_entry else str(cand.get("word", ""))),
            engine="manual_checkbox", defer=True,
        )
        page = getattr(self, "current_page", None)
        if page is not None:
            verify_pending_manual_source(self, page.stem)
    except (OSError, ValueError, TypeError, RuntimeError, AttributeError) as exc:
        _restore_pending_manual(self, pending_before)
        _restore_pending_evidence(self, evidence_before)
        self.status_var.set(f"候选未更改：人工选择未能完整暂存，{exc}")
        return False

    original_entries = list(self.entries)
    original_selections = [
        (row, "selected" in row, row.get("selected"))
        for row in [cand, *siblings]
    ]
    original_checks = []
    for row, _, _ in original_selections:
        variable = getattr(self, "candidate_check_vars", {}).get(
            str(row.get("candidate_id") or "")
        )
        if variable is not None:
            try:
                original_checks.append((variable, variable.get()))
            except (ValueError, RuntimeError, AttributeError):
                pass
    removed_entries: list[WordEntry] = []
    added_entries: list[WordEntry] = []
    try:
        for sibling in siblings:
            sibling_entry = _owned_entry_for_candidate(self, sibling)
            if sibling_entry is not None and sibling_entry in self.entries:
                self.entries.remove(sibling_entry)
                removed_entries.append(sibling_entry)
            sibling["selected"] = False
            sibling_var = self.candidate_check_vars.get(
                str(sibling.get("candidate_id", ""))
            )
            if sibling_var is not None:
                sibling_var.set(False)
        if selected:
            if entry is None:
                self.entries.append(planned_entry)
                added_entries.append(planned_entry)
            cand["selected"] = True
        else:
            if entry is not None and entry in self.entries:
                self.entries.remove(entry)
                removed_entries.append(entry)
            cand["selected"] = False
        self._sort_entries_reading_order()
        target_var = self.candidate_check_vars.get(cid)
        if target_var is not None:
            target_var.set(bool(selected))
        self._update_entry_overlays_local(
            removed=removed_entries, added=added_entries,
        )
        self._schedule_deferred_page_save(sync_editors=False)
    except Exception as exc:
        # A failed Tk row update/timer must not strand a partially switched
        # physical headword or an in-memory staged sibling override.
        self.entries[:] = original_entries
        for row, had_selected, former in original_selections:
            if had_selected:
                row["selected"] = former
            else:
                row.pop("selected", None)
        for variable, value in original_checks:
            try:
                variable.set(value)
            except Exception:
                pass
        _restore_pending_manual(self, pending_before)
        _restore_pending_evidence(self, evidence_before)
        # A previous timer may already have been cancelled. Refuse further
        # stale writes rather than guessing whether that callback survives.
        self.__dict__["_deferred_save_uncertain"] = True
        self.status_var.set(f"候选未更改：界面/延迟保存失败，请重开页面核对：{exc}")
        return False
    variant = str(cand.get("position_variant", "refined"))
    if selected and variant in {"original", "anchor"}:
        self.status_var.set("已切回原始 Y / 图像锚点 Y")
    elif selected and variant == "refined":
        self.status_var.set("已使用精修 Y")
    return True


def apply_candidate_choice(
    self, deps: ReviewSelectionDeps, cand: dict, engine: str, word: str,
) -> None:
    WordEntry = deps.WordEntry
    if not self._claim_page_for_manual_edit():
        return
    if self.__dict__.get("_deferred_save_uncertain", False):
        self.status_var.set("候选未更改：先前 PDIC/人工选择保存不确定，请重开页面核对。")
        return
    try:
        if not _manual_override_preflight(self, cand):
            return
        # OCR numerical metadata is not trusted: a malformed alternative
        # must never publish a human decision before int/float conversion.
        updated = dict(cand)
        side = cand.get(engine, {}) if engine in {"paddle", "tesseract", "lens"} else {}
        if side and not isinstance(side, dict):
            raise ValueError("候选 OCR 替代字段格式不可信")
        if side:
            for key, attr, convert in (
                ("y", "source_y", int),
                ("confidence", "confidence", float),
                ("score", "score", float),
            ):
                if side.get(key) is not None:
                    updated[attr] = convert(side[key])
        updated["word"] = word
        updated["final_engine"] = engine
        updated["selected"] = True
        updated["decision_reason"] = "manual_review_choice"
        issues = list(cand.get("issue_types", []) or [])
        if "MANUAL_OVERRIDE" not in issues:
            issues.append("MANUAL_OVERRIDE")
        updated["issue_types"] = issues
        new_entry = WordEntry(
            word, int(updated.get("source_x", 0)),
            int(updated.get("source_y", 0)),
            confidence=(float(updated.get("confidence")) if updated.get("confidence") is not None else None),
            ocr_source=engine, candidate_id=str(updated.get("candidate_id", "")),
            final_engine=engine, issue_type=",".join(issues),
            parser_score=(float(updated.get("score")) if updated.get("score") is not None else None),
            manually_selected=True,
        )
    except (OSError, ValueError, TypeError, RuntimeError, AttributeError) as exc:
        self.status_var.set(f"候选未更改：OCR 替代来源无效，{exc}")
        return

    self._sync_entry_editor_texts()
    try:
        old_entry = _owned_entry_for_candidate(self, cand)
    except RuntimeError as exc:
        self.status_var.set(f"候选未更改：{exc}")
        return
    original_entries = list(self.entries)
    original_candidate = deepcopy(cand)
    pending_before = _remember_pending_manual(self)
    page = getattr(self, "current_page", None)
    path_fn = getattr(deps, "pdic_path", None)
    try:
        if page is None or not callable(path_fn):
            raise RuntimeError("候选选择缺少可信 PDIC 页面")
        before_pdic = _bytes_or_absent(path_fn(page))
        # Defer *all* manual bytes until PDIC save. A failed PDIC writer
        # must never leave a durable manual-only candidate choice.
        self._write_manual_override(
            cand, selected=True, word=word, engine=engine, defer=True,
        )
        verify_pending_manual_source(self, page.stem)
    except (OSError, ValueError, TypeError, RuntimeError, AttributeError) as exc:
        _restore_pending_manual(self, pending_before)
        self.status_var.set(f"候选未更改：人工决定未完成暂存，{exc}")
        return

    try:
        cand.clear()
        cand.update(updated)
        if old_entry is not None and old_entry in self.entries:
            self.entries.remove(old_entry)
        self.entries.append(new_entry)
        self._sort_entries_reading_order()
        # This save preflights BOTH first-click PDIC and human source pins,
        # and commits manual_selection only after PDIC publication.
        self.save_pdic(silent=True)
        if self.__dict__.get("_pending_manual_override_payload") is not None:
            raise RuntimeError("人工选择文件尚未完成保存")
    except Exception as exc:
        # Never roll back a file to guessed bytes. If PDIC has not changed,
        # restore the old UI and in-memory staging; otherwise quarantine
        # the mixed state and require explicit reload/reconciliation.
        try:
            unchanged = _bytes_or_absent(path_fn(page)) == before_pdic
        except OSError:
            unchanged = False
        if unchanged and not self.__dict__.get("_deferred_save_uncertain", False):
            self.entries[:] = original_entries
            cand.clear()
            cand.update(original_candidate)
            _restore_pending_manual(self, pending_before)
            self.status_var.set(f"候选未保存：PDIC 未提交，已保留原候选状态：{exc}")
        else:
            self.__dict__["_deferred_save_uncertain"] = True
            self.status_var.set(
                f"候选保存结果不确定：PDIC/人工决定需重新打开核对：{exc}"
            )
        return
    self.redraw()

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

