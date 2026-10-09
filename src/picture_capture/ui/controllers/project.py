from __future__ import annotations

"""Project-entry orchestration for the main Picture Capture window.

This migration step owns only the user-facing project-selection boundary:
choosing a directory, deciding whether it is an existing/new project, and
selecting the scan-image suffix for a new project.  The larger asynchronous
``PictureCaptureApp._load_project`` state transition intentionally remains in
``app.py`` until it can be extracted independently.
"""

from pathlib import Path
from typing import Any
from tkinter import filedialog, messagebox, simpledialog

from ...models import project_page_images
from ...project_storage import has_legacy_project_data, is_managed_project


class ProjectController:
    """Coordinate opening or creating a project while the app owns loaded state."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def choose_new_project_image_suffix(self, root: Path) -> str | None:
        """Choose the scan-image extension once when creating a project."""
        app = self.app
        pages = project_page_images(root)
        if not pages:
            raise ValueError("所选目录中没有 tif/tiff/png/jpg/jpeg/bmp 扫描图片。")

        counts: dict[str, int] = {}
        for page in pages:
            suffix = page.suffix.lower()
            counts[suffix] = counts.get(suffix, 0) + 1
        suffixes = sorted(counts, key=lambda item: (-counts[item], item))
        if len(suffixes) == 1:
            return suffixes[0]

        choices = "，".join(f"{suffix}（{counts[suffix]} 张）" for suffix in suffixes)
        initial = suffixes[0]
        while True:
            value = simpledialog.askstring(
                "选择扫描图片格式",
                "检测到该文件夹包含多种扫描图片格式：\n"
                f"{choices}\n\n"
                "请输入本项目要使用的图片后缀（例如 .png 或 .tif）：",
                initialvalue=initial,
                parent=app,
            )
            if value is None:
                return None
            suffix = app._normalize_suffix(value)
            if suffix in counts:
                return suffix
            messagebox.showerror(
                "图片格式不存在",
                f"该文件夹中没有 {suffix} 扫描图片。\n可选格式：{', '.join(suffixes)}",
                parent=app,
            )
            initial = suffix

    def open_project(self) -> None:
        """Choose a project directory and hand the resolved request to the loader."""
        app = self.app
        chosen = filedialog.askdirectory(title="选择词典扫描项目目录")
        if not chosen:
            return
        try:
            root = Path(chosen)
            if is_managed_project(root) and not messagebox.askyesno(
                "既有项目",
                "此目录已经包含 Picture Capture 项目资料。是否作为既有项目打开？",
                parent=app,
            ):
                return
            existing_project = is_managed_project(root) or has_legacy_project_data(root)
            requested_suffix = None
            if not existing_project:
                requested_suffix = self.choose_new_project_image_suffix(root)
                if requested_suffix is None:
                    return
            template_root = None
            if not existing_project and messagebox.askyesno(
                "复用现有项目参数",
                "是否从另一个现有词典项目复制布局、OCR、切图等参数？\\n"
                "选择“否”将使用你保存的新项目默认参数（若无则使用内置默认）。",
                parent=app,
            ):
                source = filedialog.askdirectory(
                    title="选择要复制参数的已有项目目录",
                    parent=app,
                )
                if not source:
                    return
                template_root = Path(source)
                if template_root.expanduser().resolve() == root.expanduser().resolve():
                    messagebox.showerror(
                        "参数来源无效", "不能把新项目本身作为参数来源。", parent=app,
                    )
                    return
            app._load_project(
                root,
                requested_suffix=requested_suffix,
                launch_profile_setup=not existing_project,
                **({"parameter_template_root": template_root} if template_root is not None else {}),
            )
        except Exception as exc:
            app.show_error("无法打开项目", exc)
