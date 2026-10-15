"""Fail-closed checks before persisting explicitly refined marker positions.

Not a generic cross-file move: simplified companion data is keyed to source XY,
so any corresponding row movement is refused until an atomic transaction exists.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .project_storage import simplified_review_path_for_image
from .simplified_review import entry_key, read_records


def validate_refined_markers(
    page: Path, before: Iterable[Any], after: Iterable[Any], size: tuple[int, int],
) -> None:
    """Reject coordinate collisions, out-of-image marks and stale XY companions."""
    old, new = list(before), list(after)
    if len(old) != len(new) or any(str(a.word) != str(b.word) for a, b in zip(old, new)):
        raise ValueError("精修 Y 不得增删词条或修改词条文字")
    coords = [(int(row.x), int(row.y)) for row in new]
    if len(set(coords)) != len(coords):
        raise ValueError("精修 Y 导致重复画线坐标，已拒绝保存")
    if any(not (0 <= x < size[0] and 0 <= y < size[1]) for x, y in coords):
        raise ValueError("精修 Y 产生原图边界以外的坐标，已拒绝保存")
    moved = [(a, b) for a, b in zip(old, new)
             if (int(a.x), int(a.y)) != (int(b.x), int(b.y))]
    if not moved:
        return
    sidecar = simplified_review_path_for_image(Path(page))
    if sidecar.is_file():
        try:
            raw = json.loads(sidecar.read_text(encoding="utf-8"))
        except (ValueError, OSError, UnicodeError) as exc:
            raise ValueError("简体校对数据无法确认，禁止移动画线") from exc
        if (not isinstance(raw, dict)
                or raw.get("format") != "picture_capture_simplified_review"
                or not isinstance(raw.get("entries"), list)):
            raise ValueError("简体校对数据格式无法确认，禁止移动画线")
        stored = read_records(sidecar)
        if any(entry_key(a.x, a.y) in stored for a, _ in moved):
            raise ValueError("词条有关联简体副本，不能仅移动 PDIC；请先核对配对记录")
