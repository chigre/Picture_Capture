"""Manual proofreading form for one illustrated multilingual text group."""
from __future__ import annotations

from dataclasses import replace
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from ..illustrated_entries import IllustratedEntry


def edit_illustrated_group(parent, group: IllustratedEntry,
                           save: Callable[[IllustratedEntry], bool]) -> None:
    dialog = tk.Toplevel(parent)
    dialog.title("图解词条 / 多语言校对")
    dialog.transient(parent)
    dialog.geometry("510x500")
    root = ttk.Frame(dialog, padding=12)
    root.pack(fill="both", expand=True)
    ttk.Label(root, text="文字组：每种语言/每个印刷行输入一行").pack(anchor="w")
    lines = tk.Text(root, height=9, undo=True)
    lines.pack(fill="both", expand=True, pady=(4, 12))
    lines.insert("1.0", "\n".join(group.lines))
    ttk.Label(root, text="主索引词（默认第一行，可手动调整）").pack(anchor="w")
    main_var = tk.StringVar(value=group.primary)
    ttk.Entry(root, textvariable=main_var).pack(fill="x", pady=(3, 12))
    ttk.Label(root, text="附加别名：每行一个（多语言文字行已自动成为别名，无需重复）").pack(anchor="w")
    aliases = tk.Text(root, height=4, undo=True)
    aliases.pack(fill="both", expand=True, pady=(4, 12))
    aliases.insert("1.0", "\n".join(group.aliases))
    ttk.Label(root, text="原图矩形独立保存；本编辑只修改文字，不移动框。").pack(anchor="w")

    def commit(*_args) -> None:
        texts = tuple(v.strip() for v in lines.get("1.0", "end-1c").splitlines() if v.strip())
        extras = tuple(v.strip() for v in aliases.get("1.0", "end-1c").splitlines() if v.strip())
        primary = main_var.get().strip() or next(iter(texts), "")
        try:
            proposed = replace(group, lines=texts, aliases=extras,
                               primary=primary, status="reviewed")
            if save(proposed):
                dialog.destroy()
        except (ValueError, RuntimeError, OSError) as exc:
            messagebox.showerror("图解词条保存失败", str(exc), parent=dialog)

    row = ttk.Frame(root)
    row.pack(fill="x", pady=(10, 0))
    ttk.Button(row, text="保存并确认", command=commit).pack(side="right")
    ttk.Button(row, text="取消", command=dialog.destroy).pack(side="right", padx=7)
    dialog.bind("<Control-Return>", commit)
    lines.focus_set()
