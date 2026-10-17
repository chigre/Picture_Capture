"""Fail-closed ordinary ReviewWindow PDIC + simplified-sidecar commit.

Unlike sequential save_pdic/write_records, this writer stages exact original
and proposed bytes before touching either canonical file. It guarantees
recoverability/quarantine on failures, NOT cross-file OS-level atomicity.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .formats import pdic_path, write_pdic
from .project_storage import page_sections_read_path_for_image, simplified_review_path_for_image
from .proofreading_events import sha256_file
from .proofreading_transactions import (
    _bytes_or_absent, _publish, _recovery_path, _rollback_failed_publish,
    _stage_recovery,
)
from .simplified_review import write_records


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

    def sources_match() -> bool:
        return (
            sha256_file(page) == source.image_sha
            and _bytes_or_absent(pdic) == source.pdic_bytes
            and _bytes_or_absent(simplified) == source.simplified_bytes
            and _bytes_or_absent(source.manual_path) == source.manual_bytes
            and _bytes_or_absent(source.ocr_path) == source.ocr_bytes
            and page_sections_read_path_for_image(page) == source.section_path
            and _bytes_or_absent(source.section_path) == source.section_bytes
            and _bytes_or_absent(source.profile_path) == source.profile_bytes
        )

    if _recovery_path(page).exists() or not sources_match():
        raise RuntimeError("R3 原图/PDIC/人工决定指纹变化或存在恢复标记，拒绝保存")

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
            proposal_sidecar, page.stem, review._simplified_page_records(page.stem),
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
            if not sources_match():
                raise RuntimeError("R3 建立恢复标记后发现外部修改")
            owned = {"pdic": pdic, "simplified": simplified}
            for role, _old, new in changes:
                _publish(owned[role], new)
            if any(_bytes_or_absent(owned[role]) != new for role, _old, new in changes):
                raise RuntimeError("R3 保存回读不一致")
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
