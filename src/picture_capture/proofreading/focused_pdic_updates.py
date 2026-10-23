"""Exact-coordinate and atomic PDIC writes for focused proofreading."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class FocusedPdicDeps:
    pdic_path: object
    read_pdic: object
    replace: object
    Image: object
    _write_pdic_atomic: object


def apply_focused_review_page_updates(
    page: Path, pages: list[Path], page_index: int, changes: list[dict], *, deps: FocusedPdicDeps,
) -> tuple[list[tuple[int, int, int, str]], list[str]]:
    """Apply filtered-review edits using exact original-image X/Y only."""
    pdic_path = deps.pdic_path
    read_pdic = deps.read_pdic
    replace = deps.replace
    Image = deps.Image
    _write_pdic_atomic = deps._write_pdic_atomic
    target_path = pdic_path(page)
    original_entries = read_pdic(target_path)
    working = [replace(entry) for entry in original_entries]
    used: set[int] = set()
    planned: list[tuple[int, int, int, str]] = []
    conflicts: list[str] = []
    for change in changes:
        x, y = int(change["x"]), int(change["y"])
        original_word = str(change.get("original_word") or "")
        new_word = (
            str(change.get("new_word") or "")
            .replace("\r", " ").replace("\n", " ").replace("#", "＃").strip()
        )
        exact = [
            i for i, entry in enumerate(working)
            if i not in used and int(entry.x) == x and int(entry.y) == y
        ]
        if len(exact) > 1:
            preferred = [i for i in exact if working[i].word == original_word]
            exact = preferred or exact
        if len(exact) != 1:
            conflicts.append(f"{page.name}: ({x},{y}) {original_word}")
            continue
        entry_index = exact[0]
        used.add(entry_index)
        working[entry_index].word = new_word
        planned.append((int(page_index), x, y, new_word))
    if conflicts:
        return [], conflicts
    with Image.open(page) as opened:
        image_width = int(opened.width)
    page_links = (
        page.stem,
        pages[page_index - 1].stem if page_index > 0 else "@",
        pages[page_index + 1].stem if page_index + 1 < len(pages) else "@",
    )
    try:
        _write_pdic_atomic(target_path, working, image_width, page_links)
        verified = read_pdic(target_path)
        if len(verified) != len(working):
            raise RuntimeError("保存后 PDIC 行数发生变化")
        expected = {(row[1], row[2]): row[3] for row in planned}
        actual: dict[tuple[int, int], list[str]] = {}
        for entry in verified:
            actual.setdefault((int(entry.x), int(entry.y)), []).append(entry.word)
        for key, value in expected.items():
            if actual.get(key, []).count(value) != 1:
                raise RuntimeError(f"保存后坐标 {key} 的文本校验失败")
    except Exception:
        _write_pdic_atomic(target_path, original_entries, image_width, page_links)
        raise
    return planned, []
