from __future__ import annotations

"""UI extension for exporting a selected supervised training-page range."""

from dataclasses import replace
from datetime import datetime
from pathlib import Path
import re
import shutil
from tkinter import messagebox, simpledialog

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
    """Match a literal filename/stem only; never reinterpret a range as a number."""
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
    """Resolve '', one page, or inclusive A-B page range before PDIC filtering."""
    text = str(range_text or "").strip()
    if not text:
        return list(range(len(images))), None

    # A real filename/stem may itself contain a hyphen, so literal page identity
    # always wins.  Numeric fallback is deliberately delayed until after range
    # parsing; otherwise "000092-96" would be misread as the single page 96.
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


def export_training_package_selected_range(self) -> None:
    """Export final PDIC plus automatic baseline/corrections for one page range."""
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
    existing_all = [i for i, page in enumerate(project.images) if pdic_path(page).exists()]
    if not existing_all:
        messagebox.showinfo(
            "导出训练标记包",
            "当前项目没有已保存的 .pdic 页面。请先人工确认并保存画线结果。",
            parent=self,
        )
        return

    default_range = ""
    try:
        if self.current_page is not None:
            default_range = self.current_page.stem
    except Exception:
        default_range = ""
    range_text = simpledialog.askstring(
        "导出训练标记包｜页面范围",
        "输入要导出的页面范围：\n"
        "• 连续范围：020089-020099（也可写 89-99）\n"
        "• 单页：020093\n"
        "• 留空：全部已有 PDIC 页面\n\n"
        "只会导出范围内已经保存 PDIC 的页面。",
        initialvalue=default_range,
        parent=self,
    )
    if range_text is None:
        return
    scope, error = resolve_export_indices(list(project.images), range_text)
    if error:
        messagebox.showerror("页面范围无效", error, parent=self)
        return
    scope_set = set(scope)
    indices = [index for index in existing_all if index in scope_set]
    if not indices:
        messagebox.showinfo(
            "导出训练标记包",
            "所选页面范围内没有已保存的 .pdic 页面。",
            parent=self,
        )
        return

    first_name = project.images[indices[0]].name
    last_name = project.images[indices[-1]].name
    scope_label = first_name if len(indices) == 1 else f"{first_name} → {last_name}"
    if not messagebox.askyesno(
        "导出训练标记包",
        f"范围：{scope_label}\n"
        f"将导出其中 {len(indices)} 个已有 .pdic 的页面。\n\n"
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
                # Worker completion can be out of order; manifest order should
                # always follow the selected reading/page range.
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
