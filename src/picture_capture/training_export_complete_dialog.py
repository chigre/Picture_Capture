"""Successful training export dialog with an explicit open-folder action."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from .project_folder_launcher import open_project_folder_with_error


def show_training_export_complete(parent: object, page_count: int, zip_path: Path) -> None:
    """Show exported ZIP path and allow opening its containing directory."""
    dialog = tk.Toplevel(parent)
    dialog.title("导出训练标记包完成")
    dialog.transient(parent)
    dialog.resizable(False, False)
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    frame = ttk.Frame(dialog, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(
        frame, text=f"已导出 {page_count} 页。", justify="left",
    ).pack(anchor="w")
    ttk.Label(
        frame, text=str(zip_path), justify="left", wraplength=540,
    ).pack(anchor="w", pady=(8, 14))
    actions = ttk.Frame(frame)
    actions.pack(anchor="e")
    def open_folder() -> None:
        open_project_folder_with_error(zip_path.parent, dialog)
    ttk.Button(actions, text="打开文件夹", command=open_folder).pack(side="left", padx=(0, 8))
    ttk.Button(actions, text="关闭", command=dialog.destroy).pack(side="left")
    dialog.grab_set()
    dialog.wait_window()
