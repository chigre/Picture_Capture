"""Explicit modal warning for the destructive PPP association rewrite."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


NOTICE = "画线/插图校对后再进行本操作！"


def confirm_illustration_association(parent: tk.Misc) -> bool:
    """Buttons are *继续* and *取消*, not platform-dependent Yes/No."""
    dialog = tk.Toplevel(parent)
    dialog.title("插图关联")
    dialog.transient(parent)
    dialog.resizable(False, False)
    result = tk.BooleanVar(master=dialog, value=False)
    body = ttk.Frame(dialog, padding=(18, 15, 18, 14))
    body.pack(fill="both", expand=True)
    ttk.Label(
        body, text=f"{NOTICE}\n是否继续", justify="left",
    ).pack(anchor="w", pady=(0, 15))
    actions = ttk.Frame(body)
    actions.pack(anchor="e")

    def finish(accepted: bool) -> None:
        result.set(accepted)
        dialog.destroy()

    ttk.Button(actions, text="继续", command=lambda: finish(True)).pack(
        side="left", padx=(0, 10),
    )
    cancel = ttk.Button(actions, text="取消", command=lambda: finish(False))
    cancel.pack(side="left")
    dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
    dialog.bind("<Escape>", lambda _event: finish(False))
    dialog.grab_set()
    cancel.focus_set()
    dialog.wait_window()
    return bool(result.get())


__all__ = ["NOTICE", "confirm_illustration_association"]
