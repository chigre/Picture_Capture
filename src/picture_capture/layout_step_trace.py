"""Opt-in, read-only snapshots of the *production* Layout decision sequence.

No source images, PIL objects, Entry objects or mutable Layout instances are
retained. Snapshots are plain Python values in source-image coordinates. This
module has no Tk imports and cannot change detection or save project files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PARAMETERS = (
    "columns", "start_y", "bottom_y", "manual_x", "column_width",
    "gutter", "character_height", "row_padding",
)


def _plain_parameters(value: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    if value is None:
        return result
    for name in PARAMETERS:
        try:
            candidate = getattr(value, name)
            if candidate is not None:
                result[name] = int(candidate)
        except (AttributeError, TypeError, ValueError, OverflowError):
            pass
    return result


def _source_point(layout: Any, x: float, y: float) -> tuple[int, int]:
    try:
        return tuple(int(v) for v in layout.transform.canonical_to_source_point(
            int(round(x)), int(round(y)), layout.source_size,
        ))
    except (AttributeError, TypeError, ValueError):
        # Explicit fallback only for synthetic/test Layout objects without a
        # transform. Real product Layouts always provide canonical_to_source.
        return int(round(x)), int(round(y))


def diff_rows(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare physical row *keys*, not recycled Python object IDs."""
    old = {item["id"]: item for item in before}
    new = {item["id"]: item for item in after}
    changes: list[dict[str, Any]] = []
    for key in sorted(set(old) | set(new)):
        previous, current = old.get(key), new.get(key)
        if previous is None:
            changes.append({"id": key, "kind": "added", "before": None,
                            "after": current["role"]})
        elif current is None:
            changes.append({"id": key, "kind": "removed", "before": previous["role"],
                            "after": None})
        elif previous["role"] != current["role"]:
            changes.append({"id": key, "kind": "role", "before": previous["role"],
                            "after": current["role"]})
    return changes


@dataclass
class LayoutStepTrace:
    """Retains only geometry and small row dictionaries, never image buffers."""

    stages: list[dict[str, Any]] = field(default_factory=list)
    _last_rows: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def add_note(self, key: str, title: str, description: str,
                 *, details: dict[str, Any] | None = None) -> None:
        self.stages.append({
            "key": key, "title": title, "description": description,
            "details": dict(details or {}), "columns": [], "rows": [], "changes": [],
        })

    def add_policy(self, estimate: Any, used: Any,
                   applied: dict[str, int]) -> None:
        if estimate is not None:
            self.add_note("raw_estimate", "自动版面候选",
                          "自动检测器的原始建议；尚未按 Profile 和逐字段开关采用。",
                          details={
                              "raw": _plain_parameters(estimate),
                              "method": str(getattr(estimate, "method", "")),
                              "confidence": getattr(estimate, "confidence", None),
                          })
        else:
            self.add_note("raw_estimate", "自动版面候选",
                          "当前未启用逐页自动参数检测；没有原始自动候选。")
        self.add_note("effective_parameters", "最终采用的版面参数",
                      "以下是本次实际计算所用的 Project/Profile 参数及自动采用项。",
                      details={
                          "used": _plain_parameters(used),
                          "applied": dict(applied),
                      })

    def add_layout(self, key: str, title: str, description: str,
                   layout: Any, *, details: dict[str, Any] | None = None) -> None:
        """Freeze source-aligned rectangles at exactly one production boundary."""
        top = int(getattr(layout, "body_top", 0))
        bottom = int(getattr(layout, "body_bottom", 0))
        columns: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        for col_index, col in enumerate(getattr(layout, "columns", ()) or ()):
            left = int(getattr(col, "left", 0))
            right = int(getattr(col, "right", left))
            p0 = _source_point(layout, left, top)
            p1 = _source_point(layout, right, bottom)
            columns.append({"index": col_index, "source_start": list(p0),
                            "source_end": list(p1), "left": left,
                            "right": right, "top": top, "bottom": bottom})
            for line in getattr(col, "lines", ()) or ():
                y0 = top + int(getattr(line, "y0", 0))
                y1 = top + int(getattr(line, "y1", 0))
                p0 = _source_point(layout, left, y0)
                p1 = _source_point(layout, right, y1)
                row_id = f"C{col_index+1}-Y{y0}-{y1}"
                rows.append({
                    "id": row_id, "column": col_index,
                    "source_box": [p0[0], p0[1], p1[0], p1[1]],
                    "canonical_y": y0, "role": str(getattr(line, "role", "unknown")),
                    "first_x": float(getattr(line, "first_x", 0) or 0),
                })
        changes = diff_rows(self._last_rows, rows) if self._last_rows else []
        self.stages.append({
            "key": key, "title": title, "description": description,
            "details": dict(details or {}),
            "columns": columns, "rows": rows, "changes": changes,
        })
        self._last_rows = rows

    def final_roles(self) -> list[tuple[str, str]]:
        return [(row["id"], row["role"]) for row in self._last_rows]
