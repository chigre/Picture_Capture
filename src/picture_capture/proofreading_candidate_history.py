"""Explicit OCR-owned ReviewWindow delete history; no inferred candidate Undo.

The normal saved-text history remains in proofreading_transactions. Only the
unique, UI-owned delete that has *already* durably committed its exact plan
may enter this special replay path. All three persisted files use the existing
transient write-ahead recovery protocol; no permanent undo log is created.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from . import proofreading_transactions as tx


@dataclass(frozen=True)
class CandidateReplay:
    candidate_id: str
    selected_before: bool | None


def _owned_delete(
    before: tx.SavedSnapshot, after: tx.SavedSnapshot,
    candidate: dict[str, Any], replay: CandidateReplay, plan: Any,
) -> bool:
    cid = replay.candidate_id
    if (not cid or replay.selected_before not in (True, None)
            or before.page != after.page or not before.image_sha
            or before.image_sha != after.image_sha
            or not tx._valid_manual_path(before.page, before.manual_path)
            or before.manual_path != after.manual_path
            or before.ocr_path != after.ocr_path
            or before.ocr_bytes != after.ocr_bytes
            or before.section_path != after.section_path
            or before.section_bytes != after.section_bytes
            or before.profile_path != after.profile_path
            or before.profile_bytes != after.profile_bytes
            or before.pdic_bytes == after.pdic_bytes
            or before.manual_bytes == after.manual_bytes
            or getattr(plan, "candidate_id", None) != cid
            or after.pdic_bytes != getattr(plan, "pdic_bytes", None)
            or after.manual_bytes != getattr(plan, "manual_bytes", None)
            or after.simplified_bytes != getattr(plan, "simplified_bytes", None)):
        return False
    left, right = before.rows(), after.rows()
    owners_left, owners_right = dict(before.owner_ids), dict(after.owner_ids)
    missing = set(left) - set(right)
    if (len(missing) != 1 or set(right) - set(left)
            or set(owners_left) != set(left) or set(owners_right) != set(right)
            or owners_left[next(iter(missing))] != cid
            or sum(value == cid for value in owners_left.values()) != 1
            or any(left[key] != right[key] or owners_left[key] != owners_right[key]
                   for key in right)):
        return False
    old_candidates, new_candidates = dict(before.candidates), dict(after.candidates)
    if (len(old_candidates) != len(before.candidates)
            or len(new_candidates) != len(after.candidates)
            or set(old_candidates) != set(new_candidates)
            or cid not in old_candidates
            or any(old_candidates[key] != new_candidates[key]
                   for key in old_candidates if key != cid)
            or candidate.get("selected") is not False
            or repr(candidate) != new_candidates[cid]):
        return False
    original = dict(candidate)
    if replay.selected_before is None:
        original.pop("selected", None)
    else:
        original["selected"] = True
    if repr(original) != old_candidates[cid]:
        return False
    try:
        manual = json.loads(after.manual_bytes.decode("utf-8"))
        record = manual["overrides"][cid]
        if (manual["page"] != before.page.stem
                or record["selected"] is not False
                or record["word"] != str(left[next(iter(missing))][1])):
            return False
    except (UnicodeError, ValueError, TypeError, KeyError):
        return False
    return True


class CandidateReviewHistory(tx.ReviewSessionHistory):
    """Normal saved history plus strictly proven three-file candidate replay."""

    def __init__(self) -> None:
        super().__init__()
        self._candidate_frames: dict[int, CandidateReplay] = {}

    def invalidate(self) -> None:
        super().invalidate()
        self._candidate_frames.clear()

    def record_candidate_delete(
        self, before: tx.SavedSnapshot | None, after: tx.SavedSnapshot | None,
        candidate: dict[str, Any], selected_before: bool | None, plan: Any,
    ) -> bool:
        cid = str(candidate.get("candidate_id") or "")
        replay = CandidateReplay(cid, selected_before)
        if (before is None or after is None
                or not _owned_delete(before, after, candidate, replay, plan)):
            self.invalidate()
            return False
        if self.undo_stack and not tx._same_live_state(self.undo_stack[-1].after, before):
            self.invalidate()
        frame = tx.SavedEdit(before, after)
        self.undo_stack.append(frame)
        del self.undo_stack[:-self.max_steps]
        self.redo_stack.clear()
        self._candidate_frames = {
            id(item): self._candidate_frames[id(item)]
            for item in self.undo_stack
            if id(item) in self._candidate_frames
        }
        self._candidate_frames[id(frame)] = replay
        return True

    def record(self, before: tx.SavedSnapshot | None,
               after: tx.SavedSnapshot | None) -> bool:
        recorded = super().record(before, after)
        # New ordinary saves clear redo; discard stale candidate replay IDs.
        self._candidate_frames = {
            id(frame): self._candidate_frames[id(frame)]
            for frame in self.undo_stack + self.redo_stack
            if id(frame) in self._candidate_frames
        }
        return recorded

    def _apply(self, review: Any, *, redo: bool) -> bool:
        stack = self.redo_stack if redo else self.undo_stack
        if not stack or id(stack[-1]) not in self._candidate_frames:
            return super()._apply(review, redo=redo)
        frame = stack[-1]
        replay = self._candidate_frames[id(frame)]
        expected, target = (frame.before, frame.after) if redo else (frame.after, frame.before)
        app = review.parent
        current = tx.snapshot_review(review)
        if current is None:
            # A pending Tk repaint can be retried. Real source drift is final.
            if (getattr(app, "current_page", None) != expected.page
                    or tx.sha256_file(expected.page) != expected.image_sha
                    or tx._bytes_or_absent(tx.pdic_path(expected.page)) != expected.pdic_bytes
                    or tx._bytes_or_absent(tx.simplified_review_path_for_image(expected.page))
                       != expected.simplified_bytes
                    or tx._bytes_or_absent(expected.manual_path) != expected.manual_bytes
                    or tx._bytes_or_absent(expected.ocr_path) != expected.ocr_bytes):
                self.invalidate()
            return False
        if not tx._same_live_state(current, expected):
            self.invalidate()
            return False
        if expected.page.stem in getattr(review, "_simplified_dirty_pages", set()):
            return False
        bound = review._bound_row_entries()
        if (len(bound) != len(review.vars)
                or any(var.get().strip() != entry.word
                       for entry, var in zip(bound, review.vars))):
            return False
        matches = [row for row in getattr(app, "ocr_review_candidates", ())
                   if isinstance(row, dict)
                   and str(row.get("candidate_id") or "") == replay.candidate_id]
        if (len(matches) != 1
                or repr(matches[0]) != dict(expected.candidates).get(replay.candidate_id)):
            self.invalidate()
            return False
        # The only reversible candidate change is the original owned delete;
        # do not accept a later OCR rerun or unrelated checkbox edit.
        if not _owned_delete(frame.before, frame.after, matches[0] if not redo else
                             _candidate_after_copy(matches[0]), replay, _plan_from_after(frame.after, replay)):
            self.invalidate()
            return False
        try:
            committed = tx.publish_owned_review_bundle(
                expected, pdic_bytes=target.pdic_bytes,
                manual_bytes=target.manual_bytes,
                simplified_bytes=target.simplified_bytes,
            )
        except (OSError, RuntimeError, ValueError):
            return False
        if not committed:
            return False

        # FocusOut/async render must not capture obsolete simplified Tk rows.
        review.__dict__["_r3_simplified_capture_blocked"] = True

        # Durable commit first. Then change only the uniquely owned Entry and
        # checkbox; all surviving Entry instances keep their identity.
        app.entries[:] = [entry for entry, _, _, _ in target.entries]
        for entry, word, _, _ in target.entries:
            entry.word = word
        candidate = matches[0]
        if redo:
            candidate["selected"] = False
        elif replay.selected_before is None:
            candidate.pop("selected", None)
        else:
            candidate["selected"] = True
        check = getattr(app, "candidate_check_vars", {}).get(replay.candidate_id)
        if check is not None:
            try:
                check.set(not redo)
            except Exception:
                pass
        words = {id(entry): word for entry, word, _, _ in target.entries}
        for entry, var in zip(review._bound_row_entries(), review.vars):
            if id(entry) in words:
                var.set(words[id(entry)])
        cache = getattr(review, "_simplified_page_cache", None)
        if isinstance(cache, dict):
            cache.pop(expected.page.stem, None)
        getattr(review, "_simplified_dirty_pages", set()).discard(expected.page.stem)
        app._last_pdic_write_changed = True
        try:
            app._refresh_word_fill_check_from_line_count(
                app.current_index, len(app.entries), persist=True,
            )
            app._update_page_row(app.current_index)
        except (OSError, ValueError, AttributeError):
            pass
        stack.pop()
        (self.undo_stack if redo else self.redo_stack).append(frame)
        return True


def _candidate_after_copy(candidate: dict[str, Any]) -> dict[str, Any]:
    result = dict(candidate)
    result["selected"] = False
    return result


def _plan_from_after(after: tx.SavedSnapshot, replay: CandidateReplay) -> Any:
    # An immutable plan view, never a fresh guess from OCR or live coordinates.
    from types import SimpleNamespace
    return SimpleNamespace(
        candidate_id=replay.candidate_id,
        pdic_bytes=after.pdic_bytes,
        manual_bytes=after.manual_bytes,
        simplified_bytes=after.simplified_bytes,
    )
