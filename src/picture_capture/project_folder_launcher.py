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
