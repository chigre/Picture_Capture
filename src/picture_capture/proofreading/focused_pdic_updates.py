"""Exact-coordinate and atomic PDIC writes for focused proofreading."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .focused_crop_source_fingerprint import verify_focused_save_source

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

    # Optional at this low-level helper boundary for existing direct callers;
    # live focused-mode saves require this attestation before dispatch. If a
    # caller supplies it, all changes on the page must share the same source.
    witnessed = [
        change.get("_focused_save_source_witness") for change in changes
    ]
    expected_source = next((value for value in witnessed if value is not None), None)
    if expected_source is not None:
        if any(value != expected_source for value in witnessed):
            raise RuntimeError("筛选校对页面的原图或 SECTION 来源不一致，拒绝保存")
        verify_focused_save_source(page, expected_source)

    def disk_bytes() -> bytes | None:
        try:
            return target_path.read_bytes()
        except FileNotFoundError:
            return None

    # A source page/XY alone cannot authorize overwriting newer PDIC text.
    # Capture actual bytes (not mtime or normalized Entry objects), and
    # re-check immediately before publication. This is an optimistic guard,
    # not a cross-process OS-level atomic compare-and-swap.
    original_bytes = disk_bytes()
    original_entries = read_pdic(target_path)
    if disk_bytes() != original_bytes:
        raise RuntimeError("筛选校对 PDIC 读取期间已变化，拒绝覆盖")
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
        if str(working[entry_index].word) != original_word:
            # Even a unique exact coordinate is stale if a different user
            # or editing view already changed its original headword.
            conflicts.append(f"{page.name}: ({x},{y}) 原词已变化：{original_word}")
            continue
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
    if disk_bytes() != original_bytes:
        raise RuntimeError("筛选校对 PDIC 保存前已变化，拒绝覆盖")
    # External source changes may arrive while PDIC is read or the image
    # width is inspected. Revalidate immediately before publication.
    if expected_source is not None:
        verify_focused_save_source(page, expected_source)
    _write_pdic_atomic(target_path, working, image_width, page_links)
    # This cannot turn publication into a cross-file OS CAS. Detect source
    # drift after publication and never report verified success or roll back
    # over a foreign file.
    if expected_source is not None:
        verify_focused_save_source(page, expected_source)
    verified = read_pdic(target_path)
    if len(verified) != len(working):
        raise RuntimeError("保存后 PDIC 行数发生变化")
    # A committed target word and matching row count are not enough to
    # establish that the rest of the PDIC page survived unchanged.
    # Verify every row's word, source X/Y and order before announcing
    # success to the Tk callback. Never roll back a foreign publication.
    expected_rows = [
        (str(entry.word), int(entry.x), int(entry.y)) for entry in working
    ]
    verified_rows = [
        (str(entry.word), int(entry.x), int(entry.y)) for entry in verified
    ]
    if verified_rows != expected_rows:
        raise RuntimeError("保存后 PDIC 全部词条、坐标或顺序校验失败")
    # PDIC stores eight sidecar fields, not just words and source X/Y.
    # A foreign writer can corrupt x/y percentages or prev/next page
    # links without changing any of the Entry fields compared above.
    # The existing PDIC serializer emits UTF-8 with two-decimal percent
    # precision and g formatting; compare every ordered serialized field.
    expected_fields = []
    for entry in working:
        x, y = int(entry.x), int(entry.y)
        word = (
            str(entry.word).replace("\r", " ").replace("\n", " ")
            .replace("#", "＃").strip()
        )
        x_pct = round(x / image_width * 100, 2) if image_width else 0
        y_pct = round(y / image_width * 100, 2) if image_width else 0
        expected_fields.append([
            word, str(x), str(y), f"{x_pct:g}", f"{y_pct:g}",
            *page_links,
        ])
    published_fields = [
        line.split("#")
        for line in target_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if published_fields != expected_fields:
        # No rollback: after publication, a discrepancy may be a newer
        # writer's version. Fail closed without destroying their changes.
        raise RuntimeError("保存后 PDIC 百分比坐标或页码链接校验失败")
    expected = {(row[1], row[2]): row[3] for row in planned}
    actual: dict[tuple[int, int], list[str]] = {}
    for entry in verified:
        actual.setdefault((int(entry.x), int(entry.y)), []).append(entry.word)
    for key, value in expected.items():
        if actual.get(key, []).count(value) != 1:
            # Another writer may have changed the file after publication.
            # NEVER blindly restore an earlier snapshot over foreign bytes.
            # Preserve the exception and the visible Tk corrections for
            # deliberate operator inspection and guarded explicit retry.
            raise RuntimeError(f"保存后坐标 {key} 的文本校验失败")
    return planned, []
