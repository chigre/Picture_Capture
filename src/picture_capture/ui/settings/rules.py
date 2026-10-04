from __future__ import annotations

from pathlib import Path
from typing import Any
from tkinter import filedialog, messagebox

from ...paddle_headwords import (
    DEFAULT_HEADWORD_FILTER_RULES,
    HEADWORD_FILTER_RULES_FILENAME,
    parse_headword_filter_rules,
)
from ...project_storage import headword_filter_rules_path
from ...text_encoding import read_text_detected


def rules_path(dialog: Any) -> Path | None:
    if dialog.parent.project:
        return headword_filter_rules_path(
            dialog.parent.project.root,
            HEADWORD_FILTER_RULES_FILENAME,
        )
    return None


def load_rules_editor(dialog: Any) -> None:
    path = dialog._rules_path()
    if path and path.exists():
        text, _encoding = read_text_detected(path)
        dialog.rules_status_var.set(path.name)
    else:
        text = DEFAULT_HEADWORD_FILTER_RULES
        dialog.rules_status_var.set("尚未保存，将在保存参数时创建规则文件")
    dialog.rules_text.delete("1.0", "end")
    dialog.rules_text.insert("1.0", text)


def restore_default_rules(dialog: Any) -> None:
    if not messagebox.askyesno(
        "恢复默认规则",
        "将规则编辑框恢复为默认模板？保存参数前不会写入磁盘。",
        parent=dialog,
    ):
        return
    dialog.rules_text.delete("1.0", "end")
    dialog.rules_text.insert("1.0", DEFAULT_HEADWORD_FILTER_RULES)
    dialog.rules_status_var.set("已恢复默认模板（尚未保存）")


def import_rules(dialog: Any) -> None:
    path = filedialog.askopenfilename(
        parent=dialog,
        title="导入词头规则",
        filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
    )
    if not path:
        return
    try:
        text, _encoding = read_text_detected(path)
        parse_headword_filter_rules(text, path)
    except Exception as exc:
        messagebox.showerror("规则无效", str(exc), parent=dialog)
        return
    dialog.rules_text.delete("1.0", "end")
    dialog.rules_text.insert("1.0", text)
    dialog.rules_status_var.set(f"已导入 {Path(path).name}（尚未保存到项目）")


def export_rules(dialog: Any) -> None:
    text = dialog.rules_text.get("1.0", "end-1c")
    try:
        parse_headword_filter_rules(text, "规则编辑框")
    except Exception as exc:
        messagebox.showerror("规则无效", str(exc), parent=dialog)
        return
    path = filedialog.asksaveasfilename(
        parent=dialog,
        title="导出词头规则",
        defaultextension=".txt",
        initialfile=HEADWORD_FILTER_RULES_FILENAME,
        filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
    )
    if not path:
        return
    Path(path).write_text(text.rstrip() + "\n", encoding="utf-8")
    dialog.rules_status_var.set(f"已导出 {Path(path).name}")
