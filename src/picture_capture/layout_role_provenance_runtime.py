from __future__ import annotations

"""Expose final Layout-entry provenance in the diagnostic summary.

Physical indent lanes can be correct while a later evidence family promotes one
specific row to ``entry``.  Without provenance the overlay only shows the final
red strip, which makes a large-head/symbol override look like an indent error.
This adapter annotates diagnostic blocks from the existing Layout-line
classification registry and adds one compact source-count line to the summary.
"""

from collections import Counter
from typing import Any, Callable

from .entry_classification import get_layout_line_classification


def install_layout_role_provenance() -> None:
    from . import layout_visualization_shared as shared
    from . import layout_visualization_summary as summary

    if bool(getattr(shared, "_role_provenance_runtime_installed", False)):
        return

    original_blocks: Callable[..., Any] = shared._indent_blocks_from_understanding

    def blocks_with_source(understanding: Any) -> list[dict[str, Any]]:
        blocks = list(original_blocks(understanding) or [])
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

    original_format: Callable[..., str] = summary._format_summary

    def format_with_source(app: Any, snapshot: Any) -> str:
        text = original_format(app, snapshot)
        counts: Counter[str] = Counter()
        for block in list(getattr(app, "_layout_visualization_indent_blocks", []) or []):
            role = str(block.get("role", "body") or "body").lower()
            if role not in {"entry", "headword"}:
                continue
            source = str(block.get("entry_source", "indent") or "indent")
            counts[source] += 1
        if not counts:
            return text

        order = ("indent", "large_head", "symbol_sample", "ocr", "manual", "unknown")
        parts = [f"{name}={counts[name]}" for name in order if counts.get(name, 0)]
        parts.extend(
            f"{name}={count}"
            for name, count in sorted(counts.items())
            if name not in order
        )
        line = "entry sources: " + ", ".join(parts)
        lines = text.splitlines()
        insert_at = next(
            (index + 1 for index, value in enumerate(lines) if value.startswith("line indents:")),
            len(lines),
        )
        lines.insert(insert_at, line)
        return "\n".join(lines)

    shared._indent_blocks_from_understanding = blocks_with_source
    summary._format_summary = format_with_source
    shared._role_provenance_runtime_installed = True


__all__ = ["install_layout_role_provenance"]
