"""Direct ReviewWindow save: visible textboxes are authoritative.

This path intentionally does NOT require R3 snapshots, old simplified
source_word matches, candidate lineage or explicit history-rejoin consent.
It still uses ordinary file staging/readback so failed I/O cannot report
a successful save. The visible "√" is a display shortcut for the original
word, not literal dictionary text.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ..io.formats import pdic_path, write_pdic
from ..persistence.project_storage import simplified_review_path_for_image
from .simplified_review import read_records, write_records
from .transactions import _bytes_or_absent, _publish


def direct_save_review(review: Any) -> bool:
    """Persist ORIGINAL and SIMPLIFIED editor values, ignoring stale R3 history.

    Only a complete current-page row-to-Entry mapping is required. This
    prevents saving text into a different row during an asynchronous repaint;
    it is not a source-word/history validation.
    """
    app = review.parent
    page = getattr(app, "current_page", None)
    if page is None or getattr(app, "project", None) is None:
        raise RuntimeError("当前没有可保存的校对页面")
    rows = tuple(review._bound_row_entries())
    original_vars = tuple(review.vars)
    simplified_vars = tuple(review.simplified_vars)
    live_rows = tuple(app.entries)
    if (getattr(review, "_rendered_page_stem", None) != page.stem
            or len(rows) != len(original_vars)
            or len(rows) != len(simplified_vars)
            or len(rows) != len(live_rows)
            or len({id(row) for row in rows}) != len(rows)
            or {id(row) for row in rows} != {id(row) for row in live_rows}):
        raise RuntimeError("校对页面正在刷新；请在当前文字框显示完整后再保存")

    # Capture the two visible columns FIRST. Neither the old PDIC word nor
    # an old simplified sidecar gets to override a current visible textbox.
    originals = [str(var.get()).strip() for var in original_vars]
    simplified_display = [str(var.get()).strip() for var in simplified_vars]
    update_words = {id(row): original for row, original in zip(rows, originals)}

    new_entries = [
        replace(row, word=update_words[id(row)]) for row in live_rows
    ]
    path = pdic_path(page)
    sidecar = simplified_review_path_for_image(page)
    records = read_records(sidecar)
    manual_flags = list(getattr(review, "simplified_manual_flags", ()))
    actuals = list(getattr(review, "simplified_actual_values", ()))
    for i, (row, original, shown) in enumerate(zip(rows, originals, simplified_display)):
        # "√" means the original and simplified words are identical. It is
        # NOT the lexical value "√". Preserve auto/manual metadata for
        # unchanged displays; any newly typed simplified value becomes manual.
        text = original if shown == "√" else shown
        was_manual = bool(manual_flags[i]) if i < len(manual_flags) else False
        old_actual = actuals[i] if i < len(actuals) else None
        expected = review._simplified_display_from_value(
            str(row.word).strip(), old_actual, was_manual
        )
        manual = was_manual or shown != str(expected).strip()
        key = f"{int(row.x)},{int(row.y)}"
        records[key] = {
            "x": int(row.x), "y": int(row.y),
            "source_word": original, "text": text, "manual": manual,
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    old_pdic = _bytes_or_absent(path)
    old_sidecar = _bytes_or_absent(sidecar)
    # Serialize both proposals before changing either destination.
    with TemporaryDirectory(prefix="pc-review-save-") as directory:
        proposal_pdic = Path(directory) / "proposed.pdic"
        proposal_sidecar = Path(directory) / "proposed.json"
        write_pdic(
            proposal_pdic, new_entries, int(app.image.width), app.pages_tuple(),
        )
        write_records(proposal_sidecar, page.stem, records)
        new_pdic = proposal_pdic.read_bytes()
        new_sidecar = proposal_sidecar.read_bytes()

    changes = [
        (dest, old, new) for dest, old, new in (
            (path, old_pdic, new_pdic),
            (sidecar, old_sidecar, new_sidecar),
        ) if old != new
    ]
    try:
        for dest, old, new in changes:
            _publish(dest, new)
            if _bytes_or_absent(dest) != new:
                raise OSError("校对文件写盘后读取不一致")
    except Exception:
        # Even a publisher that raises AFTER replacing a file must be
        # rolled back. Only restore exact bytes written by THIS attempt;
        # never overwrite a different third-party revision.
        rollback_ok = True
        for dest, old, new in reversed(changes):
            try:
                current = _bytes_or_absent(dest)
                if current == old:
                    continue
                if current == new:
                    _publish(dest, old)
                    if _bytes_or_absent(dest) != old:
                        rollback_ok = False
                else:
                    rollback_ok = False
            except Exception:
                rollback_ok = False
        if not rollback_ok:
            raise OSError("校对文件部分写入，自动恢复不完整；请检查 PDIC 与简体记录")
        raise

    # Disk commit succeeded. Only now mutate Entry objects and clear edits.
    for row in live_rows:
        row.word = update_words[id(row)]
    if hasattr(review, "_simplified_page_cache"):
        review._simplified_page_cache[page.stem] = records
    if hasattr(review, "_r3_simplified_source_bytes"):
        review._r3_simplified_source_bytes[page.stem] = (
            sidecar.resolve(), new_sidecar,
        )
    for i, (original, shown) in enumerate(zip(originals, simplified_display)):
        if i < len(review.simplified_actual_values):
            review.simplified_actual_values[i] = (
                original if shown == "√" else shown
            )
        if i < len(review.simplified_manual_flags):
            key = f"{int(rows[i].x)},{int(rows[i].y)}"
            review.simplified_manual_flags[i] = bool(records[key]["manual"])
    # Once saved, a new automatic preview becomes a persisted value and
    # must not be silently regenerated on the next original-word keystroke.
    for i in range(len(getattr(review, "simplified_auto_refresh_flags", ()))):
        review.simplified_auto_refresh_flags[i] = False
    review._simplified_dirty_pages.discard(page.stem)
    app._last_pdic_write_changed = old_pdic != new_pdic

    # Prevent an older checkbox debounce from overwriting this later save.
    queued = app.__dict__.get("_deferred_save_job")
    if queued is not None:
        try:
            app.after_cancel(queued)
        except Exception:
            pass
    app.__dict__["_deferred_save_job"] = None
    app.__dict__["_deferred_save_snapshot"] = None
    app.__dict__["_deferred_save_page"] = None

    from .main_editor_sync import reconcile_main_editors_after_review
    reconcile_main_editors_after_review(app, list(rows))
    try:
        if old_pdic != new_pdic:
            app._refresh_word_fill_check_from_line_count(
                app.current_index, len(app.entries), persist=True,
            )
            app._update_page_row(app.current_index)
    except (OSError, RuntimeError, ValueError, AttributeError):
        pass
    app.status_var.set("校对保存成功：原词和简体均已按当前文本框写入。")
    return True
