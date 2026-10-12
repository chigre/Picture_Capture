"""Image-backed last-mile correction of anomalous ordinary CJK separators.

The earlier Layout-only role correction sampled LayoutLine.y0 even though
the actual rendered separators are positioned by the shared Y-refiner and
other geometric postprocessors. Worse, it retested the same first-X feature
used to make an indent mode. This independent check instead uses the
*final candidate separator locations* and requires a large, repeated,
two-column anomaly before changing any candidates.

Only a verified tall glyph at the print column front can restore an entry.
Routine pages and unmatched single outliers preserve the original result.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from .illustration_detection import _rle_components
from .models import AppSettings, Entry
from .page_understanding import uses_cjk_role_model


def _first_ink_after_separator(
    gray: np.ndarray, y: int, left: int, reference: float,
) -> float | None:
    """First sustained ink within the actual emitted candidate's next line."""
    height, width = gray.shape
    y0 = max(0, int(y))
    y1 = min(height, y0 + max(8, round(reference)))
    x0 = max(0, left - 6)
    x1 = min(width, left + max(110, round(reference * 5.2)))
    if y1 <= y0 or x1 <= x0:
        return None
    ink = gray[y0:y1, x0:x1] < 170
    active = np.flatnonzero(ink.sum(axis=0) >= max(3, round(ink.shape[0] * .14)))
    return float(x0 + int(active[0]) - left) if active.size else None


def _column_of(entry: Entry, columns: list[Any]) -> int | None:
    if not columns:
        return None
    x = int(entry.x)
    index = min(range(len(columns)), key=lambda k: abs(x - int(columns[k].left)))
    if abs(x - int(columns[index].left)) > 65:
        return None
    return index


def _verified_tall_heads(
    gray: np.ndarray, left: int, right: int, top: int, bottom: int,
    reference: float,
) -> list[tuple[int, int]]:
    x0 = max(0, left)
    x1 = min(gray.shape[1], right, left + max(110, round(reference * 5.5)))
    y0 = max(0, top)
    y1 = min(gray.shape[0], bottom)
    if x1 <= x0 or y1 <= y0:
        return []
    mask = (gray[y0:y1, x0:x1] < 170).astype(np.uint8)
    linked_image = Image.fromarray(mask * 255, "L")
    try:
        linked = np.asarray(linked_image.filter(ImageFilter.MaxFilter(3))) > 0
    finally:
        linked_image.close()
    detected: list[tuple[int, int]] = []
    for cx, cy, rx, ry, area in _rle_components(linked):
        w, h = rx - cx, ry - cy
        if (
            1.60 * reference <= w <= 3.30 * reference
            and 1.65 * reference <= h <= 3.70 * reference
            and .62 <= h / max(1, w) <= 1.75
            and area >= .25 * w * h
            and cx <= .55 * reference
        ):
            detected.append((int(cy + y0), int(h)))
    return sorted(detected)


def correct_anomalous_final_ordinary_entries(
    image: Image.Image,
    settings: AppSettings,
    layout: Any,
    entries: list[Entry],
) -> tuple[list[Entry], dict[str, Any]]:
    """Repair emitted markers only with repeated contradictions and real glyphs.

    The return is deliberately a new list; no user-edited PDIC data is read or
    changed. Triggering requires both printed indent families and a batch of
    observed contradictions at the *actual marker Y*, not LayoutLine.y0.
    """
    stats: dict[str, Any] = {
        "examined_columns": 0, "repaired_columns": [],
        "removed_false_entries": 0, "removed_glyph_fragments": 0,
        "added_verified_heads": 0,
    }
    columns = list(getattr(layout, "columns", ()) or ())
    if (
        len(columns) < 2
        or not uses_cjk_role_model(settings)
        or str(getattr(layout, "indent_type", "")) != "body"
        or str(getattr(layout.transform, "kind", "identity")) != "identity"
    ):
        return list(entries), stats

    ref = max(8.0, float(getattr(layout, "ordinary_line_height", 1.0)))
    candidates: list[tuple[int, list[Entry], float]] = []
    for index, column in enumerate(columns):
        modes = list(getattr(column, "entry_modes", ()) or ())
        body = getattr(column, "body_mode", None)
        ordinary = [
            item for item in entries
            if _column_of(item, columns) == index
            and "ordinary_layout_role" in str(getattr(item, "ocr_source", "") or "")
        ]
        if (
            body is None or not modes
            or len(getattr(column, "lines", ()) or ()) < 18
            or len(ordinary) < 12
        ):
            continue
        largest = max(int(getattr(mode, "support", 0) or 0) for mode in modes)
        stable = [
            mode for mode in modes
            if int(getattr(mode, "support", 0) or 0)
            >= max(3, round(largest * .12))
        ]
        if not stable:
            continue
        outer = min(float(mode.center) for mode in stable)
        inner = float(body.center)
        if inner - outer < .75 * ref:
            continue
        candidates.append((index, ordinary, outer + (inner - outer) * .55))
    if not candidates:
        return list(entries), stats

    gray_image = image.convert("L")
    try:
        gray = np.asarray(gray_image, dtype=np.uint8)
        rejected: set[int] = set()
        verified_columns: list[int] = []
        for index, ordinary, threshold in candidates:
            stats["examined_columns"] += 1
            left = int(columns[index].left)
            contradictions = []
            for item in ordinary:
                first = _first_ink_after_separator(gray, int(item.y), left, ref)
                if first is not None and first > threshold:
                    contradictions.append(item)
            if len(contradictions) < max(6, round(len(ordinary) * .20)):
                continue
            verified_columns.append(index)
            stats["repaired_columns"].append(index)
            rejected.update(id(item) for item in contradictions)
        if not verified_columns:
            return list(entries), stats
        output = [item for item in entries if id(item) not in rejected]
        stats["removed_false_entries"] = len(entries) - len(output)

        if not bool(getattr(settings, "profile_cjk_allow_single_headword", True)):
            return output, stats

        for index in verified_columns:
            col = columns[index]
            glyphs = _verified_tall_heads(
                gray, int(col.left), int(col.right),
                int(getattr(layout, "body_top", 0)),
                int(getattr(layout, "body_bottom", gray.shape[0])), ref,
            )
            if len(glyphs) < 3:
                continue
            kept: list[Entry] = []
            for item in output:
                if _column_of(item, columns) != index:
                    kept.append(item)
                    continue
                y = int(item.y)
                inside = any(
                    top - .52 * ref <= y < top + height - .12 * ref
                    and abs(y - top) > max(7, ref * .24)
                    for top, height in glyphs
                )
                if inside and "ordinary_bracket_pair" not in str(
                    getattr(item, "ocr_source", "") or ""
                ):
                    stats["removed_glyph_fragments"] += 1
                else:
                    kept.append(item)
            output = kept
            for top, _height in glyphs:
                if any(
                    _column_of(item, columns) == index
                    and abs(int(item.y) - top) <= max(8, ref * .30)
                    for item in output
                ):
                    continue
                item = Entry(
                    word="", x=int(col.left),
                    y=max(0, top - max(1, round(ref * .07))),
                    ocr_source="ordinary_verified_final_large_head",
                    issue_type="ORDINARY_VERIFIED_FINAL_LARGE_HEAD",
                    ocr_oversized_cjk=True,
                    ocr_single_cjk=True,
                    ocr_visual_run_height=float(_height),
                    ocr_line_height_reference=float(ref),
                )
                output.append(item)
                stats["added_verified_heads"] += 1
        return output, stats
    finally:
        gray_image.close()



def suppress_proven_bracket_body_continuations(
    image: Image.Image,
    settings: AppSettings,
    layout: Any,
    entries: list[Entry],
) -> tuple[list[Entry], list[dict[str, int | float]]]:
    """Reject only physically inset continuations after proven 【】 entries.

    A Layout false positive can appear one printed row after a bracket-proven
    entry, particularly when an enhanced display-head pass changes neighboring
    role assignments. The old bulk veto required >=6 errors and missed these
    isolated cases. This rule does NOT change the original Layout/indent
    classifier and does NOT reject another bracket- or oversized-proven entry.
    """
    columns = list(getattr(layout, "columns", ()) or ())
    if (
        len(columns) < 2
        or not uses_cjk_role_model(settings)
        or str(getattr(layout, "indent_type", "")) != "body"
        or str(getattr(layout.transform, "kind", "identity")) != "identity"
    ):
        return list(entries), []

    reference = max(8.0, float(getattr(layout, "ordinary_line_height", 1.0)))
    eligible: dict[int, float] = {}
    for index, column in enumerate(columns):
        body = getattr(column, "body_mode", None)
        modes = list(getattr(column, "entry_modes", ()) or ())
        if body is None or not modes or len(getattr(column, "lines", ()) or ()) < 16:
            continue
        supported = [
            mode for mode in modes
            if int(getattr(mode, "support", 0) or 0) >= 4
        ]
        if not supported or int(getattr(body, "support", 0) or 0) < 4:
            continue
        outer = min(float(mode.center) for mode in supported)
        inner = float(body.center)
        if inner - outer < max(16.0, .70 * reference):
            continue
        eligible[index] = outer + (inner - outer) * .57
    if not eligible:
        return list(entries), []

    by_column: dict[int, list[Entry]] = {
        i: sorted(
            (item for item in entries if _column_of(item, columns) == i),
            key=lambda item: int(item.y),
        ) for i in eligible
    }
    gray_image = image.convert("L")
    try:
        gray = np.asarray(gray_image, dtype=np.uint8)
        rejected: set[int] = set()
        events: list[dict[str, int | float]] = []
        for index, members in by_column.items():
            left = int(columns[index].left)
            for position, item in enumerate(members):
                if (
                    "ordinary_layout_role" not in str(item.ocr_source or "")
                    or bool(getattr(item, "ocr_oversized_cjk", False))
                    or position == 0
                ):
                    continue
                previous = members[position - 1]
                if "ordinary_bracket_pair" not in str(previous.ocr_source or ""):
                    continue
                gap = int(item.y) - int(previous.y)
                if not .90 * reference <= gap <= 1.70 * reference:
                    continue
                first_x = _first_ink_after_separator(
                    gray, int(item.y), left, reference,
                )
                if first_x is None or first_x <= eligible[index]:
                    continue
                rejected.add(id(item))
                events.append({
                    "column": index,
                    "y": int(item.y),
                    "prior_bracket_y": int(previous.y),
                    "first_ink_offset": round(float(first_x), 2),
                })
        return [item for item in entries if id(item) not in rejected], events
    finally:
        gray_image.close()


def suppress_blank_layout_rows_before_proven_head(
    image: Image.Image,
    settings: AppSettings,
    layout: Any,
    entries: list[Entry],
) -> tuple[list[Entry], int]:
    """Reject blank Layout-only separators immediately before proven lemmas.

    A false Layout role can anchor to orphaned phonetics. The candidate
    separator falls in a fully blank row one pitch before a verified next
    lemma. Never touch symbol/oversized entries or unproven neighboring rows.
    """
    cols = list(getattr(layout, "columns", ()) or ())
    if (
        len(cols) < 2
        or not uses_cjk_role_model(settings)
        or str(getattr(layout, "indent_type", "")) != "body"
        or str(getattr(layout.transform, "kind", "identity")) != "identity"
    ):
        return list(entries), 0

    reference = max(8.0, float(getattr(layout, "ordinary_line_height", 1.0)))
    by_column: dict[int, list[Entry]] = {
        i: [entry for entry in entries if _column_of(entry, cols) == i]
        for i in range(len(cols))
    }
    gray_image = image.convert("L")
    try:
        gray = np.asarray(gray_image, dtype=np.uint8)
        rejected: set[int] = set()
        for index, members in by_column.items():
            column = cols[index]
            left = max(0, int(column.left))
            right = min(gray.shape[1], int(column.right))
            if right <= left + reference * 3:
                continue
            for entry in members:
                if "ordinary_layout_role" not in str(entry.ocr_source or ""):
                    continue
                y = int(entry.y)
                nearby_proven = any(
                    entry is not other
                    and .85 * reference <= int(other.y) - y <= 2.05 * reference
                    and (
                        "ordinary_verified_final_large_head" in str(other.ocr_source or "")
                        or "ordinary_bracket_pair" in str(other.ocr_source or "")
                    )
                    for other in members
                )
                if not nearby_proven:
                    continue
                y0 = max(0, y)
                y1 = min(gray.shape[0], y0 + max(8, round(reference)))
                if y1 <= y0:
                    continue
                # Check the complete printed column, not only the margin.
                # A legitimate deeply indented word remains protected.
                if not np.any(gray[y0:y1, left:right] < 170):
                    rejected.add(id(entry))
        return [entry for entry in entries if id(entry) not in rejected], len(rejected)
    finally:
        gray_image.close()


__all__ = [
    "correct_anomalous_final_ordinary_entries",
    "suppress_proven_bracket_body_continuations",
    "suppress_blank_layout_rows_before_proven_head",
]
