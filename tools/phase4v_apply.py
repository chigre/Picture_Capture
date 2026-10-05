from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/picture_capture/app.py"
REVIEW = ROOT / "src/picture_capture/ui/controllers/review.py"
NEXT_STAGE = ROOT / "tests/test_next_stage_regressions.py"
REVIEW_TEST = ROOT / "tests/test_ui_review_controller.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_app() -> None:
    text = APP.read_text(encoding="utf-8")
    start = text.index("    def check_headword_order(")
    end = text.index("    def _show_text_report", start)
    replacement = (
        "    def check_headword_order(self, all_pages: bool = False) -> None:\n"
        "        self._review_controller_for_call().check_headword_order(all_pages)\n\n"
    )
    text = text[:start] + replacement + text[end:]
    APP.write_text(text, encoding="utf-8")


def patch_review_controller() -> None:
    text = REVIEW.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "import tkinter as tk\nfrom typing import Any\n",
        "import tkinter as tk\nfrom tkinter import messagebox\nfrom typing import Any\n\nfrom ...collation import LATIN_ORDER, collation_key, display_key, profile_label\nfrom ...formats import pdic_path, read_pdic\n",
        "review imports",
    )
    if "    def check_headword_order(" in text:
        raise RuntimeError("ReviewController.check_headword_order already exists")
    method = r'''

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
'''
    REVIEW.write_text(text.rstrip() + method + "\n", encoding="utf-8")


def patch_next_stage_test() -> None:
    text = NEXT_STAGE.read_text(encoding="utf-8")
    old = '''    order_start = text.index("    def check_headword_order(", app_start)
    order_end = text.index("\\n    def _show_text_report", order_start)
    order = text[order_start:order_end]
    all_pages_branch = order[order.index("        if all_pages:"):]
'''
    new = '''    order_start = text.index("    def check_headword_order(", app_start)
    order_end = text.index("\\n    def _show_text_report", order_start)
    order = text[order_start:order_end]
    assert "self._review_controller_for_call().check_headword_order(all_pages)" in order

    review_text = (root / "src" / "picture_capture" / "ui" / "controllers" / "review.py").read_text(encoding="utf-8")
    controller_start = review_text.index("    def check_headword_order(")
    controller_order = review_text[controller_start:]
    all_pages_branch = controller_order[controller_order.index("        if all_pages:"):]
'''
    text = replace_once(text, old, new, "next-stage order ownership assertions")
    NEXT_STAGE.write_text(text, encoding="utf-8")


def patch_review_test() -> None:
    text = REVIEW_TEST.read_text(encoding="utf-8")
    old = '''        "jump_to_review_candidate": "jump_to_review_candidate",
    }
'''
    new = '''        "jump_to_review_candidate": "jump_to_review_candidate",
        "check_headword_order": "check_headword_order",
    }
'''
    text = replace_once(text, old, new, "review wiring expectations")
    REVIEW_TEST.write_text(text, encoding="utf-8")


def main() -> None:
    patch_app()
    patch_review_controller()
    patch_next_stage_test()
    patch_review_test()


if __name__ == "__main__":
    main()
