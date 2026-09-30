from __future__ import annotations

"""Final OCR-independent stabilization for enhanced ordinary drawing.

The legacy VB detector and the first visual recovery pass intentionally stay
independent.  This module resolves three ambiguities only after the page has
already supplied strong visual evidence:

* visual-lane separators are re-anchored to the *next* entry line rather than
  the bottom of the preceding body line;
* oversized CJK display heads are recovered from full line projection so a
  multi-component ideograph is not required to form one connected component;
* residual VB body markers are removed once a repeated indented entry lane has
  established the page's inverted ordinary-layout polarity.
"""

from dataclasses import replace
from typing import Any

import numpy as np
from PIL import Image

from .image_utils import normalize_page_rgb
from .models import AppSettings, Entry
from .ordinary_visual import (
    _body_lane,
    _column_band_gray,
    _duplicate,
    _entry_column,
    _fill_short_gaps,
    _first_ink_lines,
    _inside_sections,
    _otsu,
    _runs,
    _source_edge,
)


def _character_height(settings: AppSettings) -> int:
    return max(8, int(round(float(getattr(settings, "character_height", 26) or 26))))


def _column_observation(
    source: Image.Image,
    geometry: Any,
    settings: AppSettings,
    column: int,
) -> tuple[int, np.ndarray, list[Any], float | None, float]:
    character_height = _character_height(settings)
    top = max(0, int(geometry.top))
    bottom = min(source.height, int(geometry.bottom))
    band = _column_band_gray(source, geometry, column, top, bottom)
    if band.size == 0:
        return top, np.zeros((0, 0), dtype=bool), [], None, float(character_height)
    ink = band <= _otsu(band)
    lines = _first_ink_lines(ink, character_height)
    baseline = _body_lane(lines, ink.shape[1], character_height)
    normal_heights = [
        int(line.y1) - int(line.y0)
        for line in lines
        if int(line.y1) > int(line.y0)
    ]
    reference = (
        float(np.median(np.asarray(normal_heights, dtype=float)))
        if normal_heights else float(character_height)
    )
    reference = max(6.0, min(float(character_height) * 1.15, reference))
    return top, ink, lines, baseline, reference


def _separator_near_next_line(
    ink: np.ndarray,
    line_y0: int,
    reference_height: float,
) -> int | None:
    """Return the last clean page row immediately before the next entry line."""
    if ink.size == 0:
        return None
    search = max(6, round(reference_height * 1.35))
    top = max(0, int(line_y0) - search)
    bottom = max(top, int(line_y0))
    if bottom <= top:
        return None
    span = max(16, min(ink.shape[1], round(ink.shape[1] * 0.97)))
    ratios = ink[top:bottom, :span].mean(axis=1)
    if ratios.size == 0:
        return None
    minimum = float(ratios.min())
    if minimum > 0.025:
        return None
    clean = ratios <= max(0.0035, minimum + 0.0035)
    clean_runs = _runs(clean)
    if not clean_runs:
        return top + int(np.argmin(ratios))
    _run_start, run_end = max(clean_runs, key=lambda pair: pair[1])
    # run_end is exclusive.  The final clean row is therefore run_end - 1,
    # which anchors the separator beside the upcoming entry rather than beside
    # the preceding definition line.
    return top + max(0, int(run_end) - 1)


def _next_line(lines: list[Any], local_y: int, reference_height: float) -> Any | None:
    lower = int(local_y) - max(2, round(reference_height * 0.10))
    upper = int(local_y) + max(10, round(reference_height * 1.70))
    candidates = [line for line in lines if lower <= int(line.y0) <= upper]
    if not candidates:
        return None
    forward = [line for line in candidates if int(line.y0) >= int(local_y)]
    pool = forward or candidates
    return min(pool, key=lambda line: abs(int(line.y0) - int(local_y)))


def _reanchor_visual_lane_entries(
    entries: list[Entry],
    geometry: Any,
    observations: dict[int, tuple[int, np.ndarray, list[Any], float | None, float]],
) -> list[Entry]:
    output: list[Entry] = []
    for entry in entries:
        source_name = str(getattr(entry, "ocr_source", "") or "")
        if source_name != "ordinary_visual_lane":
            output.append(entry)
            continue
        column = _entry_column(entry, geometry)
        top, ink, lines, _baseline, reference = observations[column]
        _u, marker_v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        local_y = int(marker_v) - int(top)
        line = _next_line(lines, local_y, reference)
        if line is None:
            output.append(entry)
            continue
        separator = _separator_near_next_line(ink, int(line.y0), reference)
        if separator is None:
            output.append(entry)
            continue
        source_y = int(top) + int(separator)
        output.append(replace(entry, y=source_y))
    return output


def _projection_runs(ink: np.ndarray, reference_height: float) -> list[tuple[int, int]]:
    if ink.size == 0:
        return []
    width = ink.shape[1]
    active = ink.sum(axis=1) >= max(2, round(width * 0.003))
    active = _fill_short_gaps(active, max(1, round(reference_height * 0.10)))
    return _runs(active)


def _recover_projection_heads(
    entries: list[Entry],
    geometry: Any,
    settings: AppSettings,
    page_sections: list[Any] | None,
    observations: dict[int, tuple[int, np.ndarray, list[Any], float | None, float]],
) -> list[Entry]:
    if not bool(getattr(settings, "profile_cjk_allow_single_headword", True)):
        return list(entries)

    recovered = list(entries)
    for column, (top, ink, _lines, baseline, reference) in observations.items():
        if ink.size == 0:
            continue
        duplicate_tolerance = max(5, round(reference * 0.65))
        for y0, y1 in _projection_runs(ink, reference):
            height = int(y1 - y0)
            if height < round(reference * 1.55):
                continue
            if height > round(reference * 3.30):
                continue
            line = ink[y0:y1]
            sturdy = line.sum(axis=0) >= max(2, round(height * 0.07))
            xs = np.flatnonzero(sturdy)
            if xs.size == 0:
                continue
            start = int(xs[0])
            maximum_start = max(
                round(reference * 2.40),
                round((float(baseline) if baseline is not None else 0.0) + reference * 2.10),
            )
            if start > maximum_start:
                continue
            # Display heads must carry substantial ink near the entry edge. This
            # rejects tall punctuation/rules and most illustrations while still
            # allowing ideographs whose radicals are disconnected components.
            edge_width = min(ink.shape[1], max(12, round(reference * 2.50)))
            edge_roi = ink[y0:y1, :edge_width]
            if edge_roi.size == 0 or float(edge_roi.mean()) < 0.035:
                continue
            separator = _separator_near_next_line(ink, y0, reference)
            if separator is None:
                continue
            source_y = int(top) + int(separator)
            if not _inside_sections(source_y, page_sections):
                continue
            if _duplicate(recovered, geometry, column, source_y, duplicate_tolerance):
                continue
            marker_x, _direction = _source_edge(geometry, column, source_y)
            recovered.append(Entry(
                word="",
                x=int(marker_x),
                y=source_y,
                confidence=0.97,
                ocr_source="ordinary_visual_head",
                issue_type="ORDINARY_OVERSIZED_HEAD_PROJECTION",
                ocr_visual_run_height=float(height),
                ocr_line_height_reference=float(reference),
                ocr_single_cjk=True,
                ocr_oversized_cjk=True,
            ))
    return recovered


def _suppress_residual_vb_body_rows(
    entries: list[Entry],
    geometry: Any,
    settings: AppSettings,
    observations: dict[int, tuple[int, np.ndarray, list[Any], float | None, float]],
) -> list[Entry]:
    visual_lanes = [
        entry for entry in entries
        if str(getattr(entry, "ocr_source", "") or "") == "ordinary_visual_lane"
    ]
    # At least three repeated recovered entry rows establish a page-level rule.
    # Once that rule exists, a column must not keep a few VB body false positives
    # merely because it failed the old >=7 / >=5 count gates.
    if len(visual_lanes) < 3:
        return list(entries)
    if not bool(getattr(settings, "profile_cjk_allow_bracketed_headword", True)):
        return list(entries)

    output: list[Entry] = []
    for entry in entries:
        if str(getattr(entry, "ocr_source", "") or "") != "ordinary_vb":
            output.append(entry)
            continue
        column = _entry_column(entry, geometry)
        top, _ink, lines, baseline, reference = observations[column]
        if baseline is None:
            output.append(entry)
            continue
        _u, marker_v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        line = _next_line(lines, int(marker_v) - int(top), reference)
        if line is None:
            output.append(entry)
            continue
        line_height = int(line.y1) - int(line.y0)
        if line_height >= reference * 1.45:
            # A large main headword is not body text.
            output.append(entry)
            continue
        if abs(float(line.start) - float(baseline)) <= max(5.0, reference * 0.70):
            continue
        output.append(entry)
    return output


def _deduplicate_visual_rows(entries: list[Entry], geometry: Any, settings: AppSettings) -> list[Entry]:
    tolerance = max(3, round(_character_height(settings) * 0.22))
    output: list[Entry] = []
    for entry in sorted(entries, key=lambda item: (int(item.y), int(item.x))):
        column = _entry_column(entry, geometry)
        _u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        duplicate_index: int | None = None
        for index, existing in enumerate(output):
            if _entry_column(existing, geometry) != column:
                continue
            _eu, ev = geometry.source_to_canonical(int(existing.x), int(existing.y))
            if abs(int(ev) - int(v)) <= tolerance:
                duplicate_index = index
                break
        if duplicate_index is None:
            output.append(entry)
            continue
        existing = output[duplicate_index]
        existing_source = str(getattr(existing, "ocr_source", "") or "")
        entry_source = str(getattr(entry, "ocr_source", "") or "")
        # Prefer explicit visual evidence over a legacy VB marker at the same Y.
        if existing_source == "ordinary_vb" and entry_source.startswith("ordinary_visual"):
            output[duplicate_index] = entry
    return output


def stabilize_ordinary_visual_entries(
    image: Image.Image,
    entries: list[Entry],
    geometry: Any,
    settings: AppSettings,
    page_sections: list[Any] | None = None,
) -> list[Entry]:
    """Finalize enhanced ordinary entries after VB + visual recovery."""
    source = normalize_page_rgb(image)
    kind = str(getattr(getattr(geometry, "transform", None), "kind", "identity") or "identity")
    if kind not in {"identity", "mirror_x"}:
        return list(entries)

    observations = {
        column: _column_observation(source, geometry, settings, column)
        for column in range(len(geometry.column_starts))
    }
    stabilized = _reanchor_visual_lane_entries(list(entries), geometry, observations)
    stabilized = _recover_projection_heads(
        stabilized, geometry, settings, page_sections, observations,
    )
    stabilized = _suppress_residual_vb_body_rows(
        stabilized, geometry, settings, observations,
    )
    return _deduplicate_visual_rows(stabilized, geometry, settings)
