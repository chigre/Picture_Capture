from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox
from typing import Any

from ...collation import LATIN_ORDER, collation_key, display_key, profile_label
from ...formats import pdic_path, read_pdic


class ReviewController:
    """Coordinate read-side OCR review lookup and main-canvas navigation.

    Durable candidate edits, PDIC/manual-override writes, and the detailed
    translucent proofreading highlight renderer remain owned by
    ``PictureCaptureApp``.  This controller owns candidate lookup/matching,
    lightweight highlight/navigation state, and headword-order report orchestration.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    def load_ocr_review_candidates(self) -> None:
        app = self.app
        app.ocr_review_candidates = []
        path = app._paddle_cache_path()
        if not path or not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            app.ocr_review_candidates = list(payload.get("review_candidates") or [])
        except Exception:
            app.ocr_review_candidates = []

    def get_review_candidate(self, candidate_id: str) -> dict | None:
        for item in self.app.ocr_review_candidates:
            if str(item.get("candidate_id", "")) == candidate_id:
                return item
        return None

    def candidate_is_selected(self, cand: dict) -> bool:
        app = self.app
        cid = str(cand.get("candidate_id", ""))
        y = int(cand.get("source_y", -99999))
        x = int(cand.get("source_x", -99999))
        for entry in app.entries:
            if cid and entry.candidate_id == cid:
                return True
            if abs(entry.x - x) <= 12 and abs(entry.y - y) <= max(
                5, round(app._quick_geometry_value("character_height") * 0.45)
            ):
                return True
        return False

    def entry_for_candidate(self, cand: dict):
        app = self.app
        cid = str(cand.get("candidate_id", ""))
        y = int(cand.get("source_y", -99999))
        x = int(cand.get("source_x", -99999))
        for entry in app.entries:
            if cid and entry.candidate_id == cid:
                return entry
            if abs(entry.x - x) <= 12 and abs(entry.y - y) <= max(
                5, round(app._quick_geometry_value("character_height") * 0.45)
            ):
                return entry
        return None

    def clear_review_entry_highlight(self) -> None:
        app = self.app
        app._review_entry_highlight_target = None
        app._review_entry_highlight_photo = None
        try:
            app.canvas.delete("proofread-entry-highlight")
        except tk.TclError:
            pass

    def highlight_review_entry(self, entry: Any) -> None:
        app = self.app
        if app.image is None or app.current_index < 0:
            return
        app._review_entry_highlight_target = (
            app.current_index,
            int(entry.x),
            int(entry.y),
        )
        app._draw_review_entry_highlight()

    def jump_to_review_candidate(self, cand: dict) -> None:
        app = self.app
        if not app.image:
            return
        y = int(cand.get("source_y", 0))
        canvas_h = max(1, app.canvas.winfo_height())
        target = max(0.0, y * app.view_scale - canvas_h * 0.30)
        total = max(1.0, app.image.height * app.view_scale)
        app.canvas.yview_moveto(min(1.0, target / total))
        app.canvas.delete("review-highlight")
        geometry = app._get_cached_display_geometry()
        col = max(0, min(len(geometry.column_starts) - 1, int(cand.get("column", 0))))
        x_source = int(cand.get("source_x", 0))
        _u, v = geometry.source_to_canonical(x_source, y)
        canonical_box = (
            geometry.x_at(col, v),
            v - 5,
            geometry.x_at(col, v) + round(geometry.column_widths[col] * 0.98),
            v + 18,
        )
        x0, y0, x1, y1 = geometry.transform.canonical_box_to_source(
            canonical_box, app.image.size
        )
        app.canvas.create_rectangle(
            x0 * app.view_scale,
            y0 * app.view_scale,
            x1 * app.view_scale,
            y1 * app.view_scale,
            outline="#00bcd4",
            width=3,
            tags=("review-highlight",),
        )
        app.canvas.tag_raise("review-highlight")

    def check_headword_order(self, all_pages: bool = False) -> None:
        app = self.app
        if not app.guard():
            return
        app.save_pdic(silent=True)
        title = "所有词头顺序核对" if all_pages else "当前页词头顺序核对"

        if all_pages:
            project = app.project
            pages = list(project.images)
            indices = list(range(len(pages)))
            sort_mode = getattr(app.settings, "headword_sort_mode", "auto")
            language = getattr(app.settings, "ocr_language", "eng")
            custom_order = getattr(app.settings, "headword_custom_order", LATIN_ORDER)
            fold_accents = getattr(app.settings, "headword_custom_fold_accents", True)
            rule = profile_label(sort_mode, language)

            def worker(index: int, _position: int, _total: int):
                page = pages[index]
                rows: list[tuple[str, str, tuple, str]] = []
                for entry in read_pdic(pdic_path(page)):
                    word = entry.word.strip()
                    if not word:
                        continue
                    rows.append((
                        page.name,
                        word,
                        collation_key(
                            word, sort_mode, language, custom_order, fold_accents,
                        ),
                        display_key(
                            word, sort_mode, language, custom_order, fold_accents,
                        ),
                    ))
                return rows

            def done(completed, total_pages, stopped, results, error):
                if error is not None:
                    return
                page_results = list(results)
                app.status_var.set(
                    f"词头读取完成 {completed}/{total_pages} 页；正在后台汇总排序…"
                )

                def finalize():
                    sequence = [
                        row
                        for page_rows in page_results
                        if isinstance(page_rows, list)
                        for row in page_rows
                    ]
                    if len(sequence) < 2:
                        return {
                            "count": len(sequence), "inversions": 0,
                            "mismatches": 0, "rule": rule, "report": "",
                            "stopped": bool(stopped), "completed": completed,
                            "total": total_pages,
                        }
                    inversions: list[
                        tuple[
                            tuple[str, str, tuple, str],
                            tuple[str, str, tuple, str],
                        ]
                    ] = []
                    for i in range(1, len(sequence)):
                        if sequence[i][2] < sequence[i - 1][2]:
                            inversions.append((sequence[i - 1], sequence[i]))
                    expected = sorted(sequence, key=lambda item: item[2])
                    mismatches = sum(
                        1 for actual, wanted in zip(sequence, expected)
                        if actual[:3] != wanted[:3]
                    )
                    lines = [
                        f"共核对 {len(sequence)} 个非空词头；发现 {len(inversions)} 处相邻逆序，"
                        f"排序后有 {mismatches} 个位置变化。",
                        f"排序规则：{rule}",
                    ]
                    if stopped:
                        lines.extend([
                            f"注意：任务提前停止，仅统计已完成的 {completed}/{total_pages} 页。",
                            "",
                        ])
                    else:
                        lines.append("")
                    lines.append("以下为相邻逆序（前一词 > 后一词）：")
                    for number, (prev, cur) in enumerate(inversions[:200], 1):
                        lines.append(
                            f"{number}. {prev[0]}  {prev[1]} [{prev[3]}]  >  "
                            f"{cur[0]}  {cur[1]} [{cur[3]}]"
                        )
                    if len(inversions) > 200:
                        lines.append(f"…另有 {len(inversions) - 200} 处未显示")
                    return {
                        "count": len(sequence), "inversions": len(inversions),
                        "mismatches": mismatches, "rule": rule,
                        "report": "\n".join(lines), "stopped": bool(stopped),
                        "completed": completed, "total": total_pages,
                    }

                def finalized(result) -> None:
                    if app.project is not project:
                        return
                    count = int(result["count"])
                    inversions = int(result["inversions"])
                    stopped_suffix = (
                        f"（提前停止，仅完成 {result['completed']}/{result['total']} 页）"
                        if result["stopped"] else ""
                    )
                    if count < 2:
                        messagebox.showinfo(
                            title,
                            f"可核对的非空词头不足 2 个。{stopped_suffix}",
                            parent=app,
                        )
                    elif not inversions:
                        messagebox.showinfo(
                            title,
                            f"顺序正常。\n共核对 {count} 个非空词头。\n"
                            f"排序规则：{result['rule']}\n{stopped_suffix}",
                            parent=app,
                        )
                    else:
                        app._show_text_report(title, str(result["report"]))
                    app.status_var.set(
                        f"{title}完成：核对 {count} 个非空词头{stopped_suffix}"
                    )

                def finalize_failed(exc, detail) -> None:
                    if detail:
                        print(detail)
                    if app.project is project:
                        app.show_error(f"{title}汇总失败", exc)

                app._start_ui_worker(
                    "headword-order-finalize", finalize, finalized, finalize_failed,
                )

            app._start_batch_task(
                "所有词头顺序核对", indices, worker, done,
                item_label=lambda i: pages[i].name,
                refresh_page_quality=False,
            )
            return

        sequence: list[tuple[str, str, tuple]] = []
        for entry in app.entries:
            word = entry.word.strip()
            if word:
                sequence.append((app.current_page.name, word, app._order_key(word)))
        if len(sequence) < 2:
            messagebox.showinfo(title, "可核对的非空词头不足 2 个。", parent=app)
            return
        inversions: list[tuple[int, tuple[str, str, tuple], tuple[str, str, tuple]]] = []
        for i in range(1, len(sequence)):
            if sequence[i][2] < sequence[i - 1][2]:
                inversions.append((i, sequence[i - 1], sequence[i]))
        expected = sorted(sequence, key=lambda item: item[2])
        mismatches = sum(1 for actual, wanted in zip(sequence, expected) if actual != wanted)
        if not inversions:
            rule = profile_label(app.settings.headword_sort_mode, app.settings.ocr_language)
            messagebox.showinfo(
                title,
                f"顺序正常。\n共核对 {len(sequence)} 个非空词头。\n排序规则：{rule}",
                parent=app,
            )
            return
        rule = profile_label(app.settings.headword_sort_mode, app.settings.ocr_language)
        lines = [
            f"共核对 {len(sequence)} 个非空词头；发现 {len(inversions)} 处相邻逆序，排序后有 {mismatches} 个位置变化。",
            f"排序规则：{rule}",
            "",
            "以下为相邻逆序（前一词 > 后一词）：",
        ]
        for number, (_i, prev, cur) in enumerate(inversions[:200], 1):
            lines.append(
                f"{number}. {prev[0]}  {prev[1]} [{app._order_display_key(prev[1])}]  >  "
                f"{cur[0]}  {cur[1]} [{app._order_display_key(cur[1])}]"
            )
        if len(inversions) > 200:
            lines.append(f"…另有 {len(inversions)-200} 处未显示")
        app._show_text_report(title, "\n".join(lines))
