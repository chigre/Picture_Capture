"""Keep main-canvas PDIC editors coherent with edits made in proofreading.

Main canvas widgets and ReviewWindow rows edit the same Entry objects, but
Tk widgets keep their own text buffers. An old canvas widget can otherwise
write its stale text back on FocusOut or at the next autosave, including after
section-aware proofreading has saved correctly.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any

from .focused_crop_source_fingerprint import _source_page_index
from .focused_visible_owner import unique_canvas_source_entries


def reconcile_main_editors_after_review(app: Any, rendered_entries: list[Any]) -> None:
    """Update only widgets whose Entry object was saved by ReviewWindow."""
    saved_ids = {id(entry) for entry in rendered_entries}
    for editor, entry in tuple(getattr(app, "entry_editor_bindings", ())):
        if id(entry) not in saved_ids:
            continue
        expected = str(entry.word)
        try:
            existing = str(editor.get())
            if existing == expected:
                continue
            editor.delete(0, "end")
            editor.insert(0, expected)
        except (tk.TclError, RuntimeError):
            # Already destroyed during navigation, or a transient Tk update.
            continue



def capture_focused_main_canvas_snapshot(app: Any):
    """Capture main Entry/widget ownership on Tk before a focused writer starts.

    A source XY only identifies a marker on disk, not the current editor
    revision. Keep object references transiently in the save callback; never
    serialize this snapshot or use it to infer persistent Entry identity.
    """
    index = getattr(app, "current_index", None)
    if index is None:
        return None
    try:
        page_index = _source_page_index(index)
    except (TypeError, ValueError, RuntimeError, OverflowError):
        return None
    bindings = tuple(getattr(app, "entry_editor_bindings", ()))
    observed = {}
    for point, entry in unique_canvas_source_entries(getattr(app, "entries", ())).items():
        buffers = []
        for editor, owner in bindings:
            if owner is not entry:
                continue
            try:
                buffers.append((editor, str(editor.get())))
            except (tk.TclError, RuntimeError):
                buffers = None
                break
        observed[point] = (entry, str(entry.word), None if buffers is None else tuple(buffers))
    return page_index, observed


def reconcile_focused_save_to_main(
    app: Any, saved_rows: list[tuple[int, int, int, str]], *, canvas_before,
) -> list[tuple[int, int]]:
    """Update a main Entry only if its pre-dispatch word and widgets are intact.

    A confirmed PDIC write is not permission to replace an independent,
    newer main-canvas human edit. Report conflicting XY for operator review;
    never rewrite a foreign widget or Entry under an aliased source point.
    """
    if canvas_before is None:
        return []
    current_index = getattr(app, "current_index", None)
    if current_index is None:
        return []
    try:
        page_owner = _source_page_index(current_index)
    except (TypeError, ValueError, RuntimeError, OverflowError):
        return []
    before_page, before_entries = canvas_before
    if before_page != page_owner:
        return []
    current_saved = {
        (x, y): word for page_index, x, y, word in saved_rows
        if int(page_index) == page_owner
    }
    if not current_saved:
        return []
    bindings = tuple(getattr(app, "entry_editor_bindings", ()))
    confirmed = []
    conflicts = []
    for point, entry in unique_canvas_source_entries(
        getattr(app, "entries", ())
    ).items():
        word = current_saved.get(point)
        if word is None:
            continue
        before = before_entries.get(point)
        if before is None or entry is not before[0] or str(entry.word) != before[1]:
            conflicts.append(point)
            continue
        earlier_buffers = before[2]
        if earlier_buffers is None:
            conflicts.append(point)
            continue
        live_editors = tuple(editor for editor, owner in bindings if owner is entry)
        if len(live_editors) != len(earlier_buffers):
            conflicts.append(point)
            continue
        try:
            unchanged = all(
                editor is prior_editor
                and old_text == before[1]
                and str(editor.get()) == old_text
                for editor, (prior_editor, old_text) in zip(live_editors, earlier_buffers)
            )
        except (tk.TclError, RuntimeError):
            unchanged = False
        if not unchanged:
            conflicts.append(point)
            continue
        entry.word = word
        entry.confidence = None
        entry.ocr_source = "manual"
        entry.final_engine = "manual"
        entry.manually_selected = True
        confirmed.append(entry)
    if confirmed:
        reconcile_main_editors_after_review(app, confirmed)
    return conflicts


def bridge_main_canvas_text_into_review(review: Any) -> int:
    """Bring independently edited main Tk words into the paired R3 save.

    Two live widgets may own the same Entry object without sharing their text
    buffers. Check ALL live bindings before changing any ReviewWindow var:
    divergent edits to the same word are a conflict, never a preference order.
    A clean main buffer is not a signal to overwrite a newer review correction.
    """
    app = review.parent
    page = getattr(app, "current_page", None)
    if (
        page is None
        or getattr(review, "_filter_rows_active", False)
        or getattr(review, "_rendered_page_stem", "") != page.stem
    ):
        return 0
    bindings = tuple(getattr(app, "entry_editor_bindings", ()))
    if not bindings:
        return 0
    rows = list(review._bound_row_entries())
    vars = tuple(review.vars)
    if len(rows) != len(vars) or len({id(x) for x in rows}) != len(rows):
        raise RuntimeError("主界面与校对界面词条绑定不同步；请核对并重新打开校对页")
    active = {id(row) for row in getattr(app, "entries", ())}
    if any(id(row) not in active for row in rows):
        raise RuntimeError("校对界面词条已失效；请先核对并刷新校对页面")
    by_id = {id(entry): (entry, var) for entry, var in zip(rows, vars)}
    changes = {}
    for editor, entry in bindings:
        if id(entry) not in active:
            continue
        try:
            text = str(editor.get()).strip()
        except (tk.TclError, RuntimeError) as exc:
            raise RuntimeError("主界面编辑框暂不可读取；修改未保存，请重试") from exc
        old = str(entry.word).strip()
        if text == old:
            continue
        owner = by_id.get(id(entry))
        if owner is None:
            raise RuntimeError("主窗口有新文字，但校对行来源尚未就绪；请核对校对页面后重试")
        review_text = str(owner[1].get()).strip()
        if review_text not in (old, text):
            raise RuntimeError("主界面与校对界面同时修改同一词条且内容不同；均已保留，请选择最终文字后保存")
        prior = changes.get(id(entry))
        if prior is not None and prior[1] != text:
            raise RuntimeError("主窗口同一词条有多个不同编辑框内容；请核对后保存")
        changes[id(entry)] = (owner[1], text)
    # Older UI sessions could already have mutated Entry.word on a main
    # FocusOut before their shared autosave was dispatched. R3 rightly
    # refuses snapshot_review if the model no longer matches the PDIC.
    # Recover this precise case only when the original ReviewWindow text is
    # independently confirmed by the on-disk, unique original-image XY.
    # A real review edit (disk matches Entry, not Review var) stays untouched.
    # Divergent main/review edits fail closed without clearing either field.
    ahead = []
    for entry, var in zip(rows, vars):
        if id(entry) in changes:
            continue
        main_word, review_word = str(entry.word).strip(), str(var.get()).strip()
        if main_word == review_word:
            continue
        attached = [editor for editor, owner in bindings if owner is entry]
        if len(attached) != 1:
            continue
        try:
            widget_text = str(attached[0].get()).strip()
        except (tk.TclError, RuntimeError) as exc:
            raise RuntimeError("主窗口编辑框状态无法核对，文字未保存") from exc
        if widget_text == main_word:
            ahead.append((entry, var, attached[0], main_word, review_word))
    restores = []
    if ahead:
        from ..io.formats import pdic_path, read_pdic
        from .focused_pdic_updates import _exact_page_coordinate
        path = pdic_path(page)
        try:
            old_bytes = path.read_bytes()
            disk_rows = read_pdic(path)
            if path.read_bytes() != old_bytes:
                raise RuntimeError("校对时 PDIC 来源发生变化")
            disk_owner = {}
            for disk_entry in disk_rows:
                xy = (
                    _exact_page_coordinate(disk_entry.x),
                    _exact_page_coordinate(disk_entry.y),
                )
                if xy in disk_owner:
                    raise RuntimeError("PDIC 重复原图坐标，无法确认保存来源")
                disk_owner[xy] = str(disk_entry.word).strip()
            for entry, var, editor, main_word, review_word in ahead:
                xy = (
                    _exact_page_coordinate(entry.x),
                    _exact_page_coordinate(entry.y),
                )
                on_disk = disk_owner.get(xy)
                if on_disk == review_word and on_disk != main_word:
                    restores.append((entry, on_disk))
                    changes[id(entry)] = (var, main_word)
                elif on_disk == main_word:
                    # This is an ordinary ReviewWindow-only edit.
                    continue
                else:
                    raise RuntimeError(
                        "主窗口与校对窗口存在不一致的文字版本；不能确定原图词条来源"
                    )
                if (
                    str(entry.word).strip() != main_word
                    or str(var.get()).strip() != review_word
                    or str(editor.get()).strip() != main_word
                ):
                    raise RuntimeError("编辑器在来源核对过程中发生变化，请重新核对")
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            raise RuntimeError("原始 PDIC 来源无法验证，输入未保存，请核对后重试") from exc
    for var, text in changes.values():
        if str(var.get()).strip() != text:
            var.set(text)
    for entry, old_word in restores:
        entry.word = old_word
    return len(changes)

def commit_proofread_entries(review: Any) -> None:
    """Persist editor words by rendered Entry identity, then reconcile canvas."""
    # This entry point runs before app.save_pdic; a marker must block edits
    # BEFORE any Entry.word or canvas binding is mutated.
    from .transactions import _recovery_path, _marker_present
    page = getattr(review.parent, "current_page", None)
    if page is not None and _marker_present(_recovery_path(page)):
        raise RuntimeError("Unresolved R3 transaction; refusing editor commit")
    bound = list(review._bound_row_entries())
    if len(bound) != len(review.vars):
        raise RuntimeError("R3 校对编辑行数已变化，拒绝丢失尚未保存的文字")
    live_ids = {id(entry) for entry in review.parent.entries}
    if any(id(entry) not in live_ids for entry in bound):
        raise RuntimeError("R3 校对词条已被重新加载，请保留输入并重新核对来源")

    # Capture simplified Tk edits while Entry.word STILL denotes the original
    # pinned PDIC word. Previously changing Entry.word first made
    # source_word_conflicts() reject this very human rename, preventing the
    # paired PDIC+simplified transaction from ever saving.
    stem = getattr(review, "_rendered_page_stem", "")
    plans = [(entry, str(entry.word), var.get().strip())
             for entry, var in zip(bound, review.vars)]
    review._capture_simplified_edits(stem)
    records_fn = getattr(review, "_simplified_page_records", None)
    records = records_fn(stem) if stem and callable(records_fn) else None
    updates = []
    for entry, old, new in plans:
        if old == new or records is None:
            continue
        # Only an exact original headword source may follow a legitimate
        # same-Entry rename. Never adopt a foreign manual record by XY alone.
        key = f"{int(entry.x)},{int(entry.y)}"
        record = records.get(key)
        if record is not None:
            if not isinstance(record, dict):
                raise RuntimeError("R3 简体副本来源记录无效，拒绝覆盖人工记录")
            if record.get("source_word") != old:
                # Direct callers must still fail closed. Only a real
                # ReviewWindow save with its frozen transaction snapshot can
                # defer a detached human record to the paired disk writer.
                if review.__dict__.get("_r3_detached_original_save_source") is None:
                    raise RuntimeError(
                        "R3 简体副本来源词条与校对原词不符，拒绝覆盖人工记录"
                    )
                continue
            updates.append((record, new))
    for record, new in updates:
        record["source_word"] = new
    for entry, _old, new in plans:
        entry.word = new
    reconcile_main_editors_after_review(review.parent, bound)
