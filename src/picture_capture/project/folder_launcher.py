"""Open a project directory in the operating system's file manager.

This action is intentionally independent from loading a Picture Capture project.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def open_project_folder(root: Path) -> None:
    """Launch the system file manager; do not wait for the launched process."""
    directory = Path(root).expanduser()
    if not directory.is_dir():
        raise FileNotFoundError(f"项目文件夹不存在：{directory}")
    if sys.platform == "win32":
        os.startfile(str(directory))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(directory)])
    else:
        subprocess.Popen(["xdg-open", str(directory)])


def open_project_folder_with_error(root: Path, parent: object) -> None:
    """GUI adapter: report unavailable directories without loading a project."""
    from tkinter import messagebox

    try:
        open_project_folder(root)
    except (OSError, RuntimeError) as exc:
        messagebox.showerror("无法打开文件夹", str(exc), parent=parent)


def add_open_folder_button(actions: object, root: Path, dialog: object, exists: bool) -> None:
    """Build the Project Center action without extending legacy GUI ownership."""
    from tkinter import ttk

    ttk.Button(
        actions, text="打开文件夹",
        command=lambda: open_project_folder_with_error(root, dialog),
        state="normal" if exists else "disabled",
    ).pack(side="left", padx=(5, 0))
