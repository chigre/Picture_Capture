"""Preserve unsaved ordinary ReviewWindow text across safe same-page repaints.

This module never writes PDIC, changes Entry.word or silently reassigns a
typing buffer by source pixel, row number, or another Entry's object ID.
"""
from __future__ import annotations

from typing import Any, Iterable


def capture_pending_review_words(
    rows: Iterable[Any], variables: Iterable[Any],
    rendered_baseline: dict[int, str], live_entries: Iterable[Any],
) -> dict[int, str]:
    """Return unsaved original-word inputs only for unchanged unique owners.

    On an unprovable dirty owner, raise before the caller destroys any Tk
    controls. A different object at the same XY is NOT the original owner.
    """
    previous_rows = tuple(rows)
    previous_vars = tuple(variables)
    current_entries = tuple(live_entries)
    if len(previous_rows) != len(previous_vars):
        raise RuntimeError("校对输入行与来源词条绑定数量不一致，拒绝刷新")
    live_ids = [id(entry) for entry in current_entries]
    if len(live_ids) != len(set(live_ids)):
        raise RuntimeError("校对当前页面有重复对象归属，拒绝刷新")
    if len({id(entry) for entry in previous_rows}) != len(previous_rows):
        raise RuntimeError("校对原词条行重复绑定，拒绝刷新")
    live_set = set(live_ids)
    pending: dict[int, str] = {}
    for entry, variable in zip(previous_rows, previous_vars):
        key = id(entry)
        try:
            actual = str(variable.get())
        except Exception as exc:
            raise RuntimeError("无法读取尚未保存的校对输入，拒绝刷新") from exc
        base = str(rendered_baseline.get(key, entry.word))
        if actual.strip() == base.strip():
            continue
        if key not in live_set or str(entry.word) != base:
            raise RuntimeError("校对文字尚未保存且词条来源版本已变化，拒绝刷新")
        pending[key] = actual
    return pending
