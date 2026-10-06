from __future__ import annotations

"""Entry-source provenance helpers for Layout diagnostics."""

from collections import Counter
from typing import Any

from .entry_classification import get_layout_line_classification
from .layout_local_indent_visualization import drift_corrected_indent_blocks


def indent_blocks_with_entry_sources(understanding: Any) -> list[dict[str, Any]]:
    """Return drift-corrected indent blocks annotated with entry provenance."""
    blocks = list(drift_corrected_indent_blocks(understanding) or [])
    layout = understanding.layout
    body_top = int(getattr(layout, "body_top", 0) or 0)
    source_by_key: dict[tuple[int, int, int], str] = {}
    for column in list(getattr(layout, "columns", []) or []):
        column_index = int(getattr(column, "index", 0) or 0)
        for line in list(getattr(column, "lines", []) or []):
            y0 = body_top + int(getattr(line, "y0", 0) or 0)
            y1 = body_top + int(getattr(line, "y1", 0) or 0)
            meta = get_layout_line_classification(line)
            source_by_key[(column_index, y0, y1)] = str(
                getattr(meta, "entry_source", "indent") or "indent"
            )

    for block in blocks:
        try:
            key = (
                int(block.get("column", 0) or 0),
                int(block["y0"]),
                int(block["y1"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        role = str(block.get("role", "body") or "body").lower()
        block["entry_source"] = (
            source_by_key.get(key, "indent")
            if role in {"entry", "headword"}
            else "body"
        )
    return blocks


def add_entry_source_summary(base_text: str, app: Any) -> str:
    """Insert the compact entry-source count line into a Layout summary."""
    counts: Counter[str] = Counter()
    for block in list(getattr(app, "_layout_visualization_indent_blocks", []) or []):
        role = str(block.get("role", "body") or "body").lower()
        if role not in {"entry", "headword"}:
            continue
        source = str(block.get("entry_source", "indent") or "indent")
        counts[source] += 1
    if not counts:
        return base_text

    order = ("indent", "large_head", "symbol_sample", "ocr", "manual", "unknown")
    parts = [f"{name}={counts[name]}" for name in order if counts.get(name, 0)]
    parts.extend(
        f"{name}={count}"
        for name, count in sorted(counts.items())
        if name not in order
    )
    line = "entry sources: " + ", ".join(parts)
    lines = base_text.splitlines()
    insert_at = next(
        (index + 1 for index, value in enumerate(lines) if value.startswith("line indents:")),
        len(lines),
    )
    lines.insert(insert_at, line)
    return "\n".join(lines)


__all__ = ["add_entry_source_summary", "indent_blocks_with_entry_sources"]
