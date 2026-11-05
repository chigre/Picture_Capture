"""Fail-closed ordinary ReviewWindow PDIC + simplified-sidecar commit.

Unlike sequential save_pdic/write_records, this writer stages exact original
and proposed bytes before touching either canonical file. It guarantees
recoverability/quarantine on failures, NOT cross-file OS-level atomicity.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ..io.formats import pdic_path, write_pdic
from ..persistence.project_storage import page_sections_read_path_for_image, simplified_review_path_for_image
from .events import sha256_file
from .transactions import (
    _bytes_or_absent, _publish, _recovery_path, _rollback_failed_publish,
    _stage_recovery, _snapshot_sources_match,
)
from .simplified_review import (
    validate_source_for_rewrite, validate_source_word_binding, read_records,
    write_records,
)


def _detached_sidecar_allows_original_only(review: Any, source, page: Path, simplified: Path, records: dict) -> bool:
    """Permit a source-pinned PDIC edit WITHOUT touching detached human JSON.

    The old manual sidecar is already mismatched BEFORE this edit. It is never
    rebound, normalized, deleted or published. Any uncertain Tk input or new
    matching source_word still fails closed.
    """
    if review.__dict__.get("_r3_detached_original_save_source") is not source:
        raise RuntimeError("R3 来源词条未由当前原词保存事务确认")
    validate_source_for_rewrite(source.simplified_bytes, page.stem)
    saved = read_records(simplified)
    # A newly rendered row with NO saved sidecar entry gets an automatic
    # OpenCC preview. The preview must neither block a safe PDIC-only edit
    # nor authorize rewriting the older detached HUMAN sidecar. Every saved
    # key/value must remain exact; verify each new key against the frozen
    # PDIC Entry, generated value, current Tk display and auto-only flags.
    if any(records.get(key) != value for key, value in saved.items()):
        raise RuntimeError("R3 旧简体副本或尚未保存的简体输入不能与原词独立提交")
    auto_seeds = {
        key: value for key, value in records.items() if key not in saved
    }
    if not auto_seeds and page.stem in review._simplified_dirty_pages:
        raise RuntimeError("R3 旧简体副本或尚未保存的简体输入不能与原词独立提交")

    old_by_id = {id(entry): (str(word), int(x), int(y))
                 for entry, word, x, y in source.entries}
    if len(old_by_id) != len(source.entries) or len(review.parent.entries) != len(old_by_id):
        raise RuntimeError("R3 原词行集合改变，旧简体副本不可独立保留")
    before_words = {(x, y): word for word, x, y in old_by_id.values()}
    if auto_seeds:
        bound = tuple(review._bound_row_entries())
        auto_flags = tuple(getattr(review, "simplified_auto_refresh_flags", ()))
        manuals = tuple(getattr(review, "simplified_manual_flags", ()))
        actuals = tuple(getattr(review, "simplified_actual_values", ()))
        if not all(len(items) == len(bound)
                   for items in (auto_flags, manuals, actuals)):
            raise RuntimeError("R3 自动简体预览缺少完整行归属，拒绝独立提交")
        proved = set()
        for index, row in enumerate(bound):
            old = old_by_id.get(id(row))
            if old is None:
                raise RuntimeError("R3 自动简体预览的原词来源已失效")
            old_word, x, y = old
            key = f"{x},{y}"
            if key not in auto_seeds:
                continue
            candidate = auto_seeds[key]
            # The row must have been absent from the original sidecar, and
            # must still be a true never-saved automatic seed. A KeyRelease,
            # paste or IME correction is never silently discarded as auto.
            if (not auto_flags[index] or manuals[index]
                    or not isinstance(candidate, dict)
                    or set(candidate) != {"x", "y", "source_word", "text", "manual"}
                    or type(candidate["x"]) is not int
                    or type(candidate["y"]) is not int
                    or candidate["x"] != x or candidate["y"] != y
                    or candidate["source_word"] != old_word
                    or candidate["manual"] is not False):
                raise RuntimeError("R3 自动简体缓存来源或人工状态无法验证")
            try:
                generated = review._auto_simplified_value(old_word)
            except (OSError, RuntimeError, TypeError, ValueError, UnicodeError) as exc:
                raise RuntimeError("R3 自动简体预览不能复核") from exc
            if (actuals[index] != generated
                    or candidate["text"] != (
                        "" if generated is None else str(generated)
                    )):
                raise RuntimeError("R3 自动简体缓存不是原词的可验证预览")
            proved.add(key)
        if proved != set(auto_seeds):
            raise RuntimeError("R3 自动简体缓存包含其他页面或未知坐标")
    after_words = {}
    changed = False
    for entry in review.parent.entries:
        old = old_by_id.get(id(entry))
        if old is None or (int(entry.x), int(entry.y)) != old[1:]:
            raise RuntimeError("R3 校对行或原图坐标归属改变，拒绝独立提交")
        xy = old[1:]
        if xy in after_words:
            raise RuntimeError("R3 同一原图坐标出现多个词条")
        after_words[xy] = str(entry.word)
        changed |= str(entry.word) != old[0]
    # A confirmed no-op must be allowed so ReviewWindow can navigate after
    # a prior PDIC-only original-word save. It cannot grant permission to
    # rebind or rewrite a detached human record; all UI/byte checks below
    # still apply, and the canonical PDIC proposal must remain byte-identical.

    stale = []
    for row in saved.values():
        xy = (int(row["x"]), int(row["y"]))
        if xy in before_words and str(row["source_word"]) != before_words[xy]:
            stale.append((xy, str(row["source_word"])))
    if not stale:
        raise RuntimeError("R3 没有已确认的历史简体来源冲突，拒绝跳过绑定检查")
    rejoining = [(xy, foreign_word) for xy, foreign_word in stale
                 if after_words.get(xy) == foreign_word]
    if rejoining:
        # Matching an old sidecar word again would silently resurrect its
        # historical manual correction. Never do this during autosave or a
        # normal Save. A distinct explicit, frozen-source operator decision
        # must authorize EXACTLY this rejoin (not an arbitrary XY match).
        if review.__dict__.get("_r3_explicit_detached_source_rejoin") is not source:
            raise RuntimeError("R3 旧简体记录可能重新归属其他词条，需要人工明确确认")
        old_words = {(int(x), int(y)): word for word, x, y
                     in ((word, x, y) for _entry, word, x, y in source.entries)}
        matching_rows = {
            (int(row["x"]), int(row["y"])): row for row in saved.values()
            if (int(row["x"]), int(row["y"])) in dict(rejoining)
        }
        if any(
            old_words.get(xy) == foreign or
            not isinstance(matching_rows.get(xy), dict) or
            not bool(matching_rows[xy].get("manual"))
            for xy, foreign in rejoining
        ):
            raise RuntimeError("R3 旧简体来源不满足原词变更及人工记录确认条件")
    # Even an explicitly rejoined record is byte-for-byte preserved in the
    # target human sidecar; the only permitted disk write is an owned PDIC.


    bound = tuple(review._bound_row_entries())
    words = tuple(getattr(review, "vars", ()))
    displayed = tuple(getattr(review, "simplified_vars", ()))
    actuals = tuple(getattr(review, "simplified_actual_values", ()))
    manuals = tuple(getattr(review, "simplified_manual_flags", ()))
    if not all(len(items) == len(bound) for items in (words, displayed, actuals, manuals)):
        raise RuntimeError("R3 校对文字控件尚未完整绑定，拒绝独立提交")
    if {id(row) for row in bound} != set(old_by_id):
        raise RuntimeError("R3 可见校对行不是当前磁盘来源")
    for i, row in enumerate(bound):
        original = str(words[i].get()).strip()
        if original != str(row.word).strip():
            raise RuntimeError("R3 原词还有尚未提交的编辑输入")
        shown = str(displayed[i].get()).strip()
        manual = bool(manuals[i])
        # An untouched automatic "√" was rendered against the PRE-EDIT
        # original. Rechecking it against the newly committed original would
        # falsely mark this display token as unsaved simplified human input,
        # blocking ordinary Save with R3-PENDING on detached-history pages.
        # A real manual simplified value still must match its live display;
        # neither the detached historical sidecar nor any human text is
        # rewritten by this original-only path.
        display_source = original if manual else old_by_id[id(row)][0]
        expected = review._simplified_display_from_value(
            display_source, actuals[i], manual,
        )
        if shown != str(expected).strip():
            raise RuntimeError("R3 简体编辑框仍有未确认输入，拒绝丢弃")
    return len(auto_seeds)


def commit_review_bundle(review: Any, source) -> None:
    app = review.parent
    if app.__dict__.get("_deferred_save_uncertain", False):
        raise RuntimeError("R3 先前保存结果不确定，禁止覆盖，需重新加载核对")
    page = app.current_page
    if (source is None or page is None or source.page != page
            or getattr(review, "_rendered_page_stem", "") != page.stem):
        raise RuntimeError("R3 无可信的本页保存快照，拒绝覆盖人工校对数据")
    pdic = pdic_path(page)
    simplified = simplified_review_path_for_image(page)

    def sources_match(published: dict[str, bytes | None] | None = None) -> bool:
        # Reuse the R3 exact source/coordinate dependencies, but acknowledge
        # only roles successfully published by THIS bundle. A foreign human
        # sidecar arriving between PDIC and simplified cannot be overwritten.
        return _snapshot_sources_match(source, published=published)

    if _recovery_path(page).exists() or not sources_match():
        raise RuntimeError("R3 原图/PDIC/人工决定指纹变化或存在恢复标记，拒绝保存")

    # A disk snapshot may be newer than this ReviewWindow's cached human text.
    # Both versions must match BEFORE writing any canonical file.
    records = review._simplified_page_records(page.stem)
    pinned = getattr(review, "_r3_simplified_source_bytes", {}).get(page.stem)
    if (pinned is None or pinned[0] != simplified.resolve()
            or pinned[1] != source.simplified_bytes):
        raise RuntimeError("R3 简体缓存来源与本次人工副本快照不一致，拒绝覆盖")
    # Compare original sidecar source_word against the *frozen pre-edit*
    # PDIC row identity. Pending editor word changes are legitimate, but an
    # already stale human correction at the same source pixel is not.
    detached_sidecar = False
    unpersisted_auto_seeds = 0
    try:
        validate_source_word_binding(
            source.simplified_bytes, page.stem,
            [(word, x, y) for _entry, word, x, y in source.entries],
        )
    except RuntimeError as error:
        if str(error) != "R3 简体记录来源词条与 PDIC 原图坐标不一致，拒绝覆盖":
            raise
        unpersisted_auto_seeds = _detached_sidecar_allows_original_only(
            review, source, page, simplified, records,
        )
        detached_sidecar = True
    if not sources_match():
        raise RuntimeError("R3 简体来源验证期间文件变化，拒绝保存")

    app._sort_entries_reading_order()
    # Use the actual production serializers for byte-exact Windows/macOS/Linux
    # representation; preview files are transient and never overwrite PDIC.
    with TemporaryDirectory(prefix="pc-r3-review-") as temp:
        proposal_pdic = Path(temp) / "proposal.pdic"
        proposal_sidecar = Path(temp) / "proposal.json"
        write_pdic(
            proposal_pdic, app.entries, int(app.image.width), app.pages_tuple(),
        )
        if not detached_sidecar:
            write_records(proposal_sidecar, page.stem, records)
        target_pdic = proposal_pdic.read_bytes()
        # A detached, preexisting human sidecar is explicitly excluded from
        # this proposal. Its exact old bytes remain the sole saved version.
        target_sidecar = (
            source.simplified_bytes if detached_sidecar
            else proposal_sidecar.read_bytes()
        )
    # New serialized human records must describe the *post-edit* Entry.
    # This must happen while files are still proposals, before the first
    # recoverable canonical file publication.
    if not detached_sidecar:
        validate_source_word_binding(
            target_sidecar, page.stem,
            [(entry.word, entry.x, entry.y) for entry in app.entries],
        )
    if detached_sidecar and all(
        str(entry.word) == str(word)
        for entry, word, _x, _y in source.entries
    ) and target_pdic != source.pdic_bytes:
        raise RuntimeError(
            "R3 原词无变化但 PDIC 序列化不同，拒绝空保存改写来源"
        )
    changes = [
        (role, former, latter)
        for role, former, latter in (
            ("pdic", source.pdic_bytes, target_pdic),
            ("simplified", source.simplified_bytes, target_sidecar),
        )
        if former != latter
    ]
    if not sources_match():
        raise RuntimeError("R3 提交前源文件发生变化，拒绝保存")

    if changes:
        marker = _stage_recovery(page, changes, rollback_required=True)
        try:
            owned = {"pdic": pdic, "simplified": simplified}
            published: dict[str, bytes | None] = {}
            for role, _old, new in changes:
                if not sources_match(published):
                    raise RuntimeError("R3 两次文件写入之间来源发生变化")
                _publish(owned[role], new)
                published[role] = new
            if not sources_match(published):
                raise RuntimeError("R3 保存回读或外部人工来源不一致")
            marker.unlink()
            if marker.exists():
                raise RuntimeError("R3 未能安全清除恢复标记")
        except Exception:
            if marker.exists():
                try:
                    _rollback_failed_publish(page)
                except (OSError, RuntimeError, ValueError):
                    # A remaining marker quarantines all later PDIC writes.
                    pass
            raise

    # ReviewWindow supersedes any queued checkbox snapshot for this page.
    # Cancel it only after the two canonical files are durably committed.
    queued = app.__dict__.get("_deferred_save_job")
    if queued is not None:
        try:
            app.after_cancel(queued)
        except Exception:
            pass
    app.__dict__["_deferred_save_job"] = None
    app.__dict__["_deferred_save_snapshot"] = None
    app.__dict__["_deferred_save_page"] = None
    review._simplified_dirty_pages.discard(page.stem)
    # A paired normal-save/delete is also authoritative for the simplified
    # cache's source pin. Otherwise the next protected sidecar write would
    # refuse the very bytes this window just committed.
    pins = getattr(review, "_r3_simplified_source_bytes", None)
    if isinstance(pins, dict) and page.stem in pins:
        pins[page.stem] = (simplified.resolve(), target_sidecar)
    changed = source.pdic_bytes != target_pdic
    app._last_pdic_write_changed = changed
    try:
        app._flush_pending_manual_override()
        app._flush_proofreading_candidate_evidence()
        app._flush_proofreading_add_evidence()
        if changed:
            app._refresh_word_fill_check_from_line_count(
                app.current_index, len(app.entries), persist=True,
            )
            app._update_page_row(app.current_index)
    except (OSError, RuntimeError, ValueError) as exc:
        app.status_var.set(f"校对文件已提交，附属状态刷新失败：{exc}")
    if detached_sidecar:
        auto_notice = (
            "本页新增的自动简体仅为预览，未写入旧人工文件。"
            if unpersisted_auto_seeds else ""
        )
        if review.__dict__.get("_r3_explicit_detached_source_rejoin") is source:
            app.status_var.set(
                "已按人工明确确认更新原词；旧人工简体副本原始字节完整保留，"
                "来源重新匹配，请核对简体内容。" + auto_notice
            )
        else:
            app.status_var.set(
                ("原词 PDIC 已保存；" if changes else "本页文字无变化，未重复写盘；")
                + "历史简体人工副本来源不一致，原始字节完整保留，"
                "未关联到新词条，请另行核对。" + auto_notice
            )
