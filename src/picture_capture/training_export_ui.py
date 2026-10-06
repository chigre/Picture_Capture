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
    """Compatibility shim for the explicit ExportController action."""
    self._export_controller_for_call().export_training_package()
