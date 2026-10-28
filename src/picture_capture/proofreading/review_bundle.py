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
from .simplified_review import validate_source_for_rewrite, write_records


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
    validate_source_for_rewrite(source.simplified_bytes, page.stem)
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
        write_records(
            proposal_sidecar, page.stem, records,
        )
        target_pdic = proposal_pdic.read_bytes()
        target_sidecar = proposal_sidecar.read_bytes()
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
