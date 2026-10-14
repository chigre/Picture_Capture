"""Explicit coordinate relocation of one existing marker, never inference.

A right-click on the exact Entry's number widget names the object that owns
the action. All validation happens before saving. Existing user PDIC remains
authoritative if optional evidence recording subsequently fails.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
import re
from tkinter import simpledialog

from ..formats import pdic_path, read_pdic
from ..page_sections import v_is_inside_sections
from ..profile_semantics import entry_allowed_by_page_template
from ..project_storage import simplified_review_path_for_image
from ..simplified_review import entry_key, read_records
from ..proofreading_events import sha256_file


def _triples(rows):
    return [(str(e.word), int(e.x), int(e.y)) for e in rows]


def _relocation_allowed(app, entry, target: tuple[int, int]) -> bool:
    """Reject geometry gaps, existing XY ownership, and paired sidecars."""
    page, image = app.current_page, app.image
    if image is None or page is None:
        return False
    x, y = target
    if not (0 <= x < image.size[0] and 0 <= y < image.size[1]):
        return False
    if any(e is not entry and (int(e.x), int(e.y)) == target for e in app.entries):
        return False
    if not app._guard_transformed_geometry("移动词条画线"):
        return False
    settings = app._current_effective_profile_settings()
    if not entry_allowed_by_page_template(
        x, y, image.size, settings, max(0, int(app.current_index)),
    ):
        return False
    geometry = app._get_cached_display_geometry()
    _, canonical_y = geometry.source_to_canonical(x, y)
    if canonical_y < geometry.top or canonical_y >= geometry.bottom:
        return False
    if app.page_sections and not v_is_inside_sections(
        canonical_y, app.page_sections, geometry.top, geometry.bottom,
    ):
        return False
    # Simplified companion sidecar keys are physical XY. Refuse moves that
    # need coordinated cross-file migration until the R3 transaction owner
    # can update both files atomically. Never leave a stale simplified key.
    sidecar = simplified_review_path_for_image(page)
    if sidecar.is_file():
        # Legacy reader intentionally converts damaged JSON to an empty map,
        # but relocation must not treat unreadable human edits as absent.
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            return False
        if (not isinstance(payload, dict)
                or payload.get("format") != "picture_capture_simplified_review"
                or not isinstance(payload.get("entries"), list)):
            return False
        old_key = entry_key(entry.x, entry.y)
        if old_key in read_records(sidecar):
            return False
    review = getattr(app, "review_window", None)
    if review is not None and getattr(review, "_rendered_page_stem", "") == page.stem:
        # Live ReviewWindow might have unsaved simplified edits or cached
        # coordinates. Refuse rather than silently desynchronize views.
        return False
    return True


def move_entry_via_dialog(app, entry):
    """One explicit user-owned movement in source pixels, with safe rollback."""
    project, page = getattr(app, "project", None), getattr(app, "current_page", None)
    status = getattr(app, "status_var", None)
    def report(message):
        if status is not None:
            status.set(message)

    if (project is None or page is None or getattr(app, "image", None) is None
            or not any(e is entry for e in getattr(app, "entries", ()))):
        return "break"
    if (getattr(app, "_batch_active", False)
            or not app._claim_page_for_manual_edit()):
        report("批处理期间禁止移动词条，避免覆盖后台 PDIC。")
        return "break"
    if (str(getattr(entry, "candidate_id", "") or "")
            or any(key in app.__dict__ for key in (
                "_pending_evidence_toggle", "_pending_evidence_add",
            ))
            or app.__dict__.get("_pending_manual_override_payload") is not None
            or app.__dict__.get("_deferred_save_snapshot") is not None):
        report("此词条关联 OCR 候选或仍有未提交操作；请先保存/完成现有操作。")
        return "break"
    raw = simpledialog.askstring(
        "移动词条画线（原图坐标）",
        f"移动当前词条到原图 X,Y（原位置 {entry.x},{entry.y}）。\n"
        "右键词条序号发起；一次只移动一个词条。\n"
        "有简体配对、OCR 候选或其他未保存编辑时会拒绝。",
        parent=app,
    )
    if raw is None:
        return "break"
    match = re.fullmatch(r"\s*(\d+)\s*[,，]\s*(\d+)\s*", raw)
    if match is None:
        report("坐标格式无效，请输入 X,Y 两个非负整数。")
        return "break"
    target = (int(match.group(1)), int(match.group(2)))
    if target == (int(entry.x), int(entry.y)):
        return "break"
    if page != getattr(app, "current_page", None):
        report("页面在坐标输入期间发生变化；未移动。")
        return "break"
    try:
        app._sync_entry_editor_texts()
        disk = pdic_path(page)
        prior_sha = sha256_file(disk)
        old_rows = read_pdic(disk)
        if prior_sha is None or sha256_file(disk) != prior_sha:
            report("PDIC 在读取期间发生变化，未移动。")
            return "break"
        old_xy = (int(entry.x), int(entry.y))
        located = [r for r in old_rows if (int(r.x), int(r.y)) == old_xy]
        if len(located) != 1:
            report("原词条坐标在 PDIC 中不唯一或不存在，未移动。")
            return "break"
        old = (str(located[0].word), *old_xy)
        old_counter = Counter(_triples(old_rows))
        live_counter = Counter(_triples(app.entries))
        live_counter.subtract(Counter([(str(entry.word), *old_xy)]))
        old_counter.subtract(Counter([old]))
        if (+live_counter) != (+old_counter) or (
            len({(e.x, e.y) for e in old_rows}) != len(old_rows)
        ):
            report("同页还有其他未保存/重复坐标的词条；先保存再移动。")
            return "break"
        if not _relocation_allowed(app, entry, target):
            report("目标无效、位于 Profile/SECTION 外或关联简体配对/审核页；未移动。")
            return "break"
        image_sha = sha256_file(page)
        if image_sha is None:
            report("原始图像缺失，未移动。")
            return "break"
        if bool(getattr(app.settings, "proofreading_event_capture", False)):
            # Before touching PDIC, ensure any existing journal is current,
            # unambiguous, and tied to the very image being moved.
            from ..proofreading_capture import _owned_ids_at_saved_snapshot, _project_identity
            from ..project_storage import data_root
            from uuid import NAMESPACE_URL, uuid5
            relative = page.resolve().relative_to(Path(project.root).resolve()).as_posix()
            page_id = f"{_project_identity(Path(project.root))}/{relative}"
            journal = (data_root(Path(project.root)) / "ProofreadingEvidence"
                       / f"{uuid5(NAMESPACE_URL, relative).hex}.json")
            valid, _ = _owned_ids_at_saved_snapshot(
                journal, page_id=page_id, prior_pdic_sha256=prior_sha,
                image_sha256=image_sha, required_before=(old,),
            )
            if not valid:
                report("词条历史身份或日志不匹配；请先检查来源，未移动。")
                return "break"
        if page != app.current_page or sha256_file(disk) != prior_sha or sha256_file(page) != image_sha:
            report("页面或来源在保存前变化，未移动。")
            return "break"
        entry.x, entry.y = target
        try:
            app.save_pdic(silent=True, sync_editors=False)
        except Exception:
            if sha256_file(disk) == prior_sha:
                entry.x, entry.y = old_xy
                app._sort_entries_reading_order()
                report("PDIC 写入失败，已恢复未提交坐标，未生成证据。")
            else:
                report("PDIC 已改变但后续保存阶段失败；不回滚磁盘，未确认操作证据。")
            return "break"
        evidence_warning = None
        if bool(getattr(app.settings, "proofreading_event_capture", False)):
            try:
                from ..proofreading_capture import capture_saved_explicit_marker_move
                captured = capture_saved_explicit_marker_move(
                    project_root=Path(project.root), page=page,
                    prior_pdic_entries=old_rows, prior_pdic_sha256=prior_sha,
                    before=old,
                    after=(str(entry.word), int(entry.x), int(entry.y)),
                    prior_image_sha256=image_sha,
                )
                if not captured:
                    evidence_warning = "画线已保存，但身份证据未能证明唯一操作；没有追加日志。"
            except (OSError, ValueError, TypeError):
                evidence_warning = "画线已保存，但校对证据写入失败；PDIC 为准。"
        app._sort_entries_reading_order()
        app.redraw()
        report(evidence_warning or f"已移动词条画线到原图 X,Y={target[0]},{target[1]}。")
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        report(f"无法移动词条：{exc}")
    return "break"
