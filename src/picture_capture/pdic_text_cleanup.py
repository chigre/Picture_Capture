"""Clear PDIC word text without changing its marker coordinates or metadata."""
from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

from .formats import pdic_path, read_pdic, read_text_detected, write_text_atomic


def clear_pdic_words(path: Path) -> int:
    """Atomically erase word fields, preserving all other PDIC columns.

    Validate the complete source before writing: malformed input must not be
    silently corrupted by a destructive bulk action.
    """
    path = Path(path)
    if not path.is_file():
        return 0
    entries = read_pdic(path)
    text, _encoding = read_text_detected(path)
    changed = sum(bool(entry.word) for entry in entries)
    if not changed:
        return 0
    lines = text.splitlines(keepends=True)
    output = []
    for line in lines:
        if not line.strip():
            output.append(line)
            continue
        prefix, separator, suffix = line.partition("#")
        if not separator:
            raise ValueError(f"{path.name}: PDIC record has no separator")
        output.append(separator + suffix)
    write_text_atomic(path, "".join(output))
    return changed


def clear_selected_scope(self) -> None:
        """Clear word fields in the selected page range, never marker geometry."""
        if not self.guard():
            return
        if self._batch_active:
            messagebox.showinfo("清除文本", "已有批量任务运行，请结束后再清除文本。", parent=self)
            return
        try:
            indices = tuple(int(i) for i in self.selected_page_indices())
        except Exception as exc:
            self.show_error("页面范围无效", exc)
            return
        project = self.project
        if project is None:
            return
        pages = tuple(project.images)
        indices = tuple(i for i in indices if 0 <= i < len(pages))
        if not indices:
            messagebox.showinfo("清除文本", "当前选择的页码范围为空。", parent=self)
            return
        if not messagebox.askyesno(
            "确认批量清除词条文本",
            f"将清空所选 {len(indices)} 页 PDIC 词条中的文字，保留全部画线坐标。"
            "\\n这会覆盖原有词条文字，不能直接撤销。确认执行吗？",
            parent=self,
        ):
            return
        # Save the currently edited page before background changes, otherwise
        # the next foreground autosave could restore old text from memory.
        self.save_pdic(silent=True)

        def worker(index: int, _position: int, _total: int):
            return index, clear_pdic_words(pdic_path(pages[index]))

        def done(completed, total, stopped, results, error):
            processed = {index for index, _count in results}
            if self.current_index in processed:
                for entry in self.entries:
                    entry.word = ""
                self.redraw()
            count = sum(count for _index, count in results)
            if error is None:
                status = "已停止" if stopped else "完成"
                self.status_var.set(
                    f"清除文本{status}：处理 {completed}/{total} 页，清空 {count} 条词条文字。"
                )

        self._start_batch_task(
            "清除文本",
            indices,
            worker,
            done,
            item_label=lambda index: pages[index].name,
        )
