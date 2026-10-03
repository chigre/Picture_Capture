from __future__ import annotations

"""UI extension for exporting supervised training pages.

Training export deliberately reuses the main-window page selection.  The user
chooses Current / Current-to-end / Specified once in the normal page-range bar;
export must not maintain a second, potentially divergent range state.
"""

from dataclasses import replace
from datetime import datetime
from pathlib import Path
import re
import shutil
from tkinter import messagebox

from . import __version__
from .formats import pdic_path
from .project_storage import training_exports_root
from .training_export import (
    TrainingExportCancelled,
    copy_project_context,
    export_training_page,
    make_training_zip,
    write_training_manifest,
)


def _page_number(text: str) -> int | None:
    stem = Path(str(text)).stem
    match = re.search(r"(\d+)$", stem)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _resolve_exact_name(images: list[Path], text: str) -> int | None:
    """Match a literal filename/stem only; retained for compatibility/tests."""
    value = str(text or "").strip().casefold()
    if not value:
        return None
    for index, page in enumerate(images):
        if value in {page.name.casefold(), page.stem.casefold()}:
            return index
    return None


def _resolve_endpoint(images: list[Path], text: str) -> int | None:
    value = str(text or "").strip()
    if not value:
        return None
    exact = _resolve_exact_name(images, value)
    if exact is not None:
        return exact
    number = _page_number(value)
    if number is not None:
        matches = [
            index for index, page in enumerate(images)
            if _page_number(page.name) == number
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def resolve_export_indices(
    images: list[Path],
    range_text: str,
) -> tuple[list[int], str | None]:
    """Legacy-compatible standalone range parser.

    The export button no longer calls this parser; it uses the main window's
    ``selected_page_indices()`` so every batch operation shares one range state.
    """
    text = str(range_text or "").strip()
    if not text:
        return list(range(len(images))), None

    exact = _resolve_exact_name(images, text)
    if exact is not None:
        return [exact], None

    parts = re.split(r"\s*(?:-|–|—|~|～|至|到)\s*", text, maxsplit=1)
    if len(parts) == 2 and parts[0] and parts[1]:
        start = _resolve_endpoint(images, parts[0])
        end = _resolve_endpoint(images, parts[1])
        if start is None or end is None:
            return [], "范围端点没有匹配到项目页面，请检查页名/页码。"
        if start > end:
            start, end = end, start
        return list(range(start, end + 1)), None

    one = _resolve_endpoint(images, text)
    if one is not None:
        return [one], None
    return [], "请输入单页或连续范围，例如 020093 或 020089-020099。"


def _main_scope_label(self, indices: list[int]) -> str:
    """Human-readable description of the already-selected main-window scope."""
    if not self.project or not indices:
        return "无"
    first_name = self.project.images[indices[0]].name
    last_name = self.project.images[indices[-1]].name
    mode = self.page_range_var.get() if hasattr(self, "page_range_var") else "current"
    if len(indices) == 1:
        return first_name
    if mode == "to_end":
        return f"当前至末页：{first_name} → {last_name}"
    if mode == "specified":
        spec = self.page_range_spec_var.get().strip() if hasattr(self, "page_range_spec_var") else ""
        return f"指定：{spec or (first_name + ' → ' + last_name)}"
    return f"{first_name} → {last_name}"


def export_training_package_selected_range(self) -> None:
    """Export final PDIC plus automatic baseline/corrections for main UI scope."""
    if not self.project or self._batch_active:
        if self._batch_active:
            self.status_var.set("已有批量任务正在运行，请结束后再导出训练标记包。")
        return
    if any(
        str(token[0]).startswith("training-cleanup-")
        for token in self._ui_worker_active
    ):
        self.status_var.set("上一轮训练导出仍在清理临时文件；清理完成后再重新导出。")
        return
    try:
        if self.current_page is not None and self.image is not None:
            self._save_current_page_by_mode()
    except Exception as exc:
        self.show_error("导出前保存当前页失败", exc)
        return

    project = self.project
    # Single source of truth: exactly the same scope used by drawing, OCR,
    # illustration detection and cropping.  Do not ask for a second range here.
    try:
        selected = list(self.selected_page_indices())
    except Exception as exc:
        self.show_error("读取主界面页面范围失败", exc)
        return
    selected = sorted({int(index) for index in selected if 0 <= int(index) < len(project.images)})
    if not selected:
        messagebox.showinfo(
            "导出训练标记包",
            "主界面当前页面范围没有有效页面。请先在页面列表上方选择范围。",
            parent=self,
        )
        return

    indices = [index for index in selected if pdic_path(project.images[index]).exists()]
    if not indices:
        messagebox.showinfo(
            "导出训练标记包",
            "主界面当前页面范围内没有已保存的 .pdic 页面。请先人工确认并保存画线结果。",
            parent=self,
        )
        return

    scope_label = _main_scope_label(self, selected)
    skipped = len(selected) - len(indices)
    skipped_text = f"\n其中 {skipped} 页没有 PDIC，将自动跳过。" if skipped else ""
    if not messagebox.askyesno(
        "导出训练标记包",
        f"使用主界面页面范围：{scope_label}\n"
        f"将导出 {len(indices)} 个已有 .pdic 的页面。{skipped_text}\n\n"
        "每页会同时保存：\n"
        "1. 程序普通画线的自动 baseline（优先使用当时捕获的原始快照）；\n"
        "2. 当前人工增删后的最终 PDIC；\n"
        "3. added / deleted / moved / unchanged 逐条差异；\n"
        "4. 页面排版/indent family 诊断与 OCR/PPP 上下文。\n\n"
        "如果旧页面没有历史 baseline，导出时会非破坏性重跑一次，并明确标记为 recomputed。\n\n"
        "请确认最终 PDIC 已人工校对。继续？",
        parent=self,
    ):
        return

    export_root = training_exports_root(project.root)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    base_name = f"{project.root.name}_training_{stamp}"
    staging = export_root / f".{base_name}_building"
    zip_path = export_root / f"{base_name}.zip"
    settings = replace(self.settings)
    page_records: list[dict] = []
    context_files: list[str] = []
    items: list[object] = ["__prepare__"] + list(indices) + ["__finalize__"]
    page_order = {project.images[index].name: pos for pos, index in enumerate(indices)}

    def cleanup_partial() -> None:
        shutil.rmtree(staging, ignore_errors=True)
        zip_path.with_name(f".{zip_path.name}.tmp").unlink(missing_ok=True)

    def worker(item, _position: int, _total: int):
        try:
            if item == "__prepare__":
                export_root.mkdir(parents=True, exist_ok=True)
                cleanup_partial()
                staging.mkdir(parents=True, exist_ok=True)
                context_files[:] = copy_project_context(project.root, staging)
                return {"prepared": True}
            if item == "__finalize__":
                if self._batch_stop_event.is_set():
                    raise TrainingExportCancelled("训练标记包导出已停止")
                page_records.sort(
                    key=lambda row: page_order.get(str(row.get("page") or ""), 10**9)
                )
                write_training_manifest(
                    staging,
                    project_name=project.root.name,
                    settings=settings,
                    pages=page_records,
                    context_files=context_files,
                    software_version=__version__,
                )
                make_training_zip(
                    staging, zip_path,
                    should_stop=self._batch_stop_event.is_set,
                )
                shutil.rmtree(staging, ignore_errors=True)
                return {"final_zip": str(zip_path)}
            index = int(item)
            record = export_training_page(
                project.images[index], project.root, settings, staging, index,
            )
            page_records.append(record)
            return record
        except TrainingExportCancelled:
            cleanup_partial()
            return {"cancelled": True}
        except Exception:
            cleanup_partial()
            raise

    def labeler(item) -> str:
        if item == "__prepare__":
            return "准备 staging 并复制项目上下文"
        if item == "__finalize__":
            return "生成 supervised dataset_manifest.json 和 ZIP"
        return project.images[int(item)].name

    def done(_completed, _total, stopped, results, error):
        if error is not None:
            return
        produced = next(
            (str(row.get("final_zip")) for row in reversed(results)
             if isinstance(row, dict) and row.get("final_zip")),
            "",
        )
        if produced:
            self.status_var.set(f"训练标记包已导出：{Path(produced).name}")
            messagebox.showinfo(
                "导出训练标记包完成",
                f"已导出 {len(page_records)} 页。\n\n{produced}",
                parent=self,
            )
            return
        if stopped:
            self.status_var.set("训练标记包已停止；正在后台清理 staging…")

            def cleanup_worker():
                cleanup_partial()
                return True

            def cleanup_done(_result) -> None:
                if self.project is project:
                    self.status_var.set("训练标记包导出已停止；未生成不完整数据包。")

            self._start_ui_worker(
                f"training-cleanup-{base_name}",
                cleanup_worker, cleanup_done,
                lambda exc, detail: print(detail or str(exc)),
                wait_on_close=True,
            )

    self._start_batch_task(
        "导出训练标记包", items, worker, done, item_label=labeler,
    )
