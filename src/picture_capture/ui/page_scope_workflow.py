"""Canonical native-call owners for page scope workflow.

Keep Tk callback ABI and original patched collaborators through live frozen
dependencies. The owner never imports the heavyweight app shell.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from pathlib import Path

@dataclass(frozen=True)
class PageScopeDeps:
    re: object
    bookmarked_page_indices: object
    messagebox: object
    ocr_cache_root: object
    compact_ocr_cache_file: object
    json: object


def _page_number(deps: PageScopeDeps, path: Path) -> int | None:
    re = deps.re
    match = re.search(r"(\d+)(?!.*\d)", path.stem)
    return int(match.group(1)) if match else None

def _parse_page_spec(self, deps: PageScopeDeps, spec: str) -> list[int]:
    re = deps.re
    if not self.project: return []
    tokens = [item.strip() for item in re.split(r"[,，]", spec) if item.strip()]
    if not tokens:
        raise ValueError("请填写指定页面范围，例如 0008-0020,0025,0030~0035。")
    # A numeric range denotes actual numbered page filenames (0001.png,
    # 0002.png, ...), not every filename whose final component happens to
    # be numeric. This keeps auxiliary scans such as 0000_01.png out of
    # ``1-100`` while retaining the historical ordinal fallback for
    # projects that have no purely numeric filenames at all.
    numeric_page_indices: dict[int, list[int]] = {}
    trailing_number_indices: dict[int, list[int]] = {}
    for index, page in enumerate(self.project.images):
        number = self._page_number(page)
        if number is not None:
            trailing_number_indices.setdefault(number, []).append(index)
        if page.stem.isdigit():
            numeric_page_indices.setdefault(int(page.stem), []).append(index)
    selected: list[int] = []
    for token in tokens:
        # Accept the range notations users commonly type/paste on Windows:
        # 0008-0020, 0008~0020, 0008～0020, 0008–0020, 0008—0020.
        # Leading zeroes are intentionally preserved in the input but page
        # matching is numeric so both 8 and 0008 resolve to page 0008.
        range_match = re.fullmatch(r"\s*(\d+)\s*[-~～–—−]\s*(\d+)\s*", token)
        if range_match:
            lo, hi = sorted((int(range_match.group(1)), int(range_match.group(2))))
            page_number_indices = numeric_page_indices or trailing_number_indices
            if page_number_indices:
                missing = [number for number in range(lo, hi + 1) if number not in page_number_indices]
                if missing:
                    shown = ", ".join(str(number) for number in missing[:12])
                    suffix = " …" if len(missing) > 12 else ""
                    raise ValueError(f"页面范围中以下页码不存在：{shown}{suffix}")
                selected.extend(
                    index
                    for number in range(lo, hi + 1)
                    for index in page_number_indices[number]
                )
            elif 1 <= lo <= hi <= len(self.project.images):
                selected.extend(range(lo - 1, hi))
            else:
                raise ValueError(f"页面范围超出项目：{token}")
        elif token.isdigit():
            number = int(token)
            if number in numeric_page_indices:
                selected.extend(numeric_page_indices[number])
            elif not numeric_page_indices and number in trailing_number_indices:
                selected.extend(trailing_number_indices[number])
            elif 1 <= number <= len(self.project.images):
                selected.append(number - 1)
            else:
                raise ValueError(f"找不到第 {number} 页。")
        else:
            raise ValueError(
                f"页面范围格式错误：{token}。可使用 0008-0020、0008~0020，多个范围用逗号分隔。"
            )
    return sorted(set(selected))

def selected_page_indices(self, deps: PageScopeDeps) -> list[int]:
    bookmarked_page_indices = deps.bookmarked_page_indices
    if not self.project: return []
    mode = self.page_range_var.get() if hasattr(self, "page_range_var") else "current"
    if mode == "current": return [self.current_index] if self.current_index >= 0 else []
    if mode == "bookmarks":
        return bookmarked_page_indices(self.project.images, self._bookmark_stems())
    if mode == "to_end": return list(range(max(0, self.current_index), len(self.project.images)))
    if mode == "to_specified":
        indices = self._parse_page_spec(self.page_range_spec_var.get())
        if len(indices) != 1:
            raise ValueError("当前至指定页需要输入一个结束页码")
        end = indices[0]
        return list(range(min(self.current_index, end), max(self.current_index, end) + 1))
    return self._parse_page_spec(self.page_range_spec_var.get())

def _paddle_temp_matches_page(deps: PageScopeDeps, path: Path, page_stem: str) -> bool:
    """Return True only for PaddleOCR temp entries owned by one page stem."""
    name = path.name
    stem = str(page_stem or "")
    if not stem or name == stem:
        return bool(stem and name == stem)
    return any(
        name.startswith(stem + suffix)
        for suffix in (".", "_", "-")
    )

def cleanup_paddleocr_temp_selected_scope(self, deps: PageScopeDeps) -> None:
    """Compact PaddleOCR cache for the selected pages without losing reusable OCR."""
    messagebox = deps.messagebox
    ocr_cache_root = deps.ocr_cache_root
    compact_ocr_cache_file = deps.compact_ocr_cache_file
    json = deps.json
    if not self.project:
        messagebox.showinfo("压缩OCR缓存", "请先打开项目。", parent=self)
        return
    try:
        indices = self.selected_page_indices()
    except Exception as exc:
        self.show_error("页面范围无效", exc)
        return
    if not indices:
        messagebox.showinfo("压缩OCR缓存", "当前页面范围为空。", parent=self)
        return

    cache_root = ocr_cache_root(self.project.root)
    if not cache_root.exists():
        messagebox.showinfo(
            "压缩OCR缓存",
            "当前项目没有 PaddleOCR 缓存可压缩。",
            parent=self,
        )
        return

    page_stems = [
        self.project.images[index].stem
        for index in indices
        if 0 <= int(index) < len(self.project.images)
    ]
    sidecar_suffixes = (
        "_ocr_diagnostics.txt", "_ocr_comparison.txt", "_issues.tsv",
        "_ocr_engines.tsv", "_fusion.tsv",
    )

    def human_size(size: int) -> str:
        value = float(max(0, size))
        units = ("B", "KB", "MB", "GB", "TB")
        for unit in units:
            if value < 1024.0 or unit == units[-1]:
                return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024.0
        return f"{size} B"

    existing_pages = 0
    estimated_bytes = 0
    legacy_sidecars = 0
    for stem in page_stems:
        cache_path = cache_root / f"{stem}.json"
        found = False
        paths = [cache_path]
        paths.extend(cache_root / f"{stem}{suffix}" for suffix in sidecar_suffixes)
        for path in paths:
            if not path.exists() or not path.is_file():
                continue
            found = True
            try:
                estimated_bytes += int(path.stat().st_size)
            except OSError:
                pass
            if path != cache_path:
                legacy_sidecars += 1
        if found:
            existing_pages += 1

    if not existing_pages:
        messagebox.showinfo(
            "压缩OCR缓存",
            f"所选 {len(indices)} 页没有对应的 PaddleOCR 缓存。",
            parent=self,
        )
        return

    confirmed = messagebox.askyesno(
        "压缩 PaddleOCR 缓存",
        (
            f"将优化所选范围内 {existing_pages} 页的 PaddleOCR 数据。\n\n"
            f"当前相关缓存/诊断约 {human_size(estimated_bytes)}；"
            f"发现 {legacy_sidecars} 个旧式可再生诊断文件。\n\n"
            "操作会：\n"
            "• 将 <page>.json 改写为紧凑缓存，只保留复用 OCR、Project Profile 诊断和校对所需信息；\n"
            "• 删除重复的 diagnostics/comparison/issues/engines/fusion 文本副本；\n"
            "• 保留 <page>_manual_selection.json 人工选择；\n"
            "• 保留 OCR 原始记录，因此之后正常“复用缓存”无需重新 OCR。\n\n"
            "原始扫描图、PDIC/PPP、词条文字和人工校对结果均不修改。是否继续？"
        ),
        icon="warning",
        parent=self,
    )
    if not confirmed:
        return

    before_total = 0
    after_total = 0
    removed_sidecars = 0
    compacted = 0
    failed: list[str] = []
    for stem in page_stems:
        cache_path = cache_root / f"{stem}.json"
        try:
            before, after, removed = compact_ocr_cache_file(cache_path)
            if before <= 0 and removed <= 0:
                continue
            before_total += before
            after_total += after
            removed_sidecars += removed
            compacted += 1
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            failed.append(f"{stem}: {exc}")

    released = max(0, before_total - after_total)
    summary = (
        f"已优化 {compacted} 页 PaddleOCR 缓存；"
        f"删除 {removed_sidecars} 个重复诊断文件；"
        f"释放约 {human_size(released)}"
    )
    self.status_var.set(summary)
    if failed:
        messagebox.showwarning(
            "OCR缓存压缩部分完成",
            summary + "\n\n以下页面未能压缩：\n" + "\n".join(failed[:12])
            + ("\n…" if len(failed) > 12 else ""),
            parent=self,
        )
        return
    messagebox.showinfo(
        "OCR缓存压缩完成",
        summary + "\n\n人工选择、可复用 OCR 原始记录、PDIC/PPP 和校对结果均已保留。",
        parent=self,
    )

def jump_to_page_spec(self, deps: PageScopeDeps) -> None:
    """Navigate to the first page number typed in the specified-range box."""
    re = deps.re
    messagebox = deps.messagebox
    match = re.search(r"\d+", self.page_range_spec_var.get())
    if not match:
        messagebox.showinfo("跳到页面", "请先在“指定”文本框输入页码。", parent=self)
        return
    try:
        indices = self._parse_page_spec(match.group(0))
    except ValueError as exc:
        self.show_error("无法定位页面", exc)
        return
    if indices:
        self.page_range_var.set("specified")
        self.load_page(indices[0])

