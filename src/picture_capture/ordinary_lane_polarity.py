from __future__ import annotations

"""Pure-visual page-level polarity correction for ordinary drawing.

Some dictionaries invert the historical Draw_Auto assumption: dense body text
starts at the physical column edge while the real subentries live on a repeated
indented lane.  In that layout the faithful VB detector can fire on nearly
every body row.

This module deliberately does *not* depend on OCR language, dictionary profile,
or parser switches.  A secondary entry lane must prove itself from page pixels:
it has to repeat, sit distinctly away from the dominant body lane, and show a
stable marker-like leading shape.  Only then may dense legacy body markers be
suppressed and the proven secondary boundaries be emitted.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image

from .image_utils import normalize_page_rgb
from .models import AppSettings, Entry
from .ordinary_visual import (
    _body_lane,
    _cluster_lines,
    _column_band_gray,
    _first_ink_lines,
    _otsu,
    _patch_similarity,
    _separator_above,
    _source_edge,
)


@dataclass(slots=True)
class _PolarityEvidence:
    active: bool
    body_line_y0: tuple[int, ...] = ()
    secondary_line_y0: tuple[int, ...] = ()
    secondary_separator_y: tuple[int, ...] = ()
    baseline: float = 0.0
    secondary_center: float = 0.0
    legacy_count: int = 0
    body_supported_legacy: int = 0


def _entry_column(entry: Entry, geometry: Any) -> int:
    u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
    return min(
        range(len(geometry.column_starts)),
        key=lambda column: abs(int(u) - int(geometry.x_at(column, int(v)))),
    )


def _secondary_lane_evidence(
    ink: np.ndarray,
    character_height: int,
) -> tuple[float | None, list[Any], list[Any]]:
    """Return body baseline, body rows, and strongest repeated indented lane."""
    lines = _first_ink_lines(ink, character_height)
    baseline = _body_lane(lines, ink.shape[1], character_height)
    if baseline is None:
        return None, [], []

    body_lines = [
        line for line in lines
        if abs(float(line.start) - float(baseline)) <= character_height * 0.60
    ]
    candidates = [
        line for line in lines
        if (
            baseline + character_height * 0.90
            <= line.start
            <= baseline + character_height * 3.70
        )
    ]

    best: list[Any] = []
    best_score = -1.0
    for cluster in _cluster_lines(candidates, character_height * 0.55):
        if len(cluster) < 4:
            continue
        for line in cluster:
            similarities = [
                _patch_similarity(line.patch, other.patch)
                for other in cluster if other is not line
            ]
            line.max_similarity = max(similarities) if similarities else 0.0
        marker_rows = [line for line in cluster if line.max_similarity >= 0.50]
        if len(marker_rows) < 3:
            continue
        marker_fraction = len(marker_rows) / float(len(cluster))
        if marker_fraction < 0.45:
            continue
        lane_center = float(np.median([line.start for line in marker_rows]))
        if lane_center - float(baseline) < character_height * 0.85:
            continue
        score = len(marker_rows) + marker_fraction
        if score > best_score:
            best = marker_rows
            best_score = score
    return baseline, body_lines, best


def _legacy_marker_followed_by_body_line(
    marker_y: int,
    body_line_y0: tuple[int, ...],
    character_height: int,
) -> bool:
    """VB markers sit in whitespace immediately above the line they describe."""
    lower = max(1, round(character_height * 0.05))
    upper = max(lower + 1, round(character_height * 1.20))
    return any(lower <= int(line_y) - int(marker_y) <= upper for line_y in body_line_y0)


def _inside_sections(y: int, page_sections: list[Any] | None) -> bool:
    if not page_sections:
        return True
    return any(int(section.top_v) <= int(y) < int(section.bottom_v) for section in page_sections)


def _column_polarity_evidence(
    source: Image.Image,
    entries: list[Entry],
    geometry: Any,
    settings: AppSettings,
    column: int,
) -> _PolarityEvidence:
    character_height = max(
        8, int(round(float(getattr(settings, "character_height", 26) or 26)))
    )
    top = max(0, int(geometry.top))
    bottom = min(source.height, int(geometry.bottom))
    band = _column_band_gray(source, geometry, column, top, bottom)
    if band.size == 0:
        return _PolarityEvidence(False)
    threshold = _otsu(band)
    ink = band <= threshold
    baseline, body_lines, secondary = _secondary_lane_evidence(
        ink, character_height,
    )
    if baseline is None or len(secondary) < 3 or len(body_lines) < 8:
        return _PolarityEvidence(False)

    legacy = [
        entry for entry in entries
        if str(entry.ocr_source or "") == "ordinary_vb"
        and _entry_column(entry, geometry) == column
    ]
    if len(legacy) < 8:
        return _PolarityEvidence(False)

    body_y = tuple(int(top + line.y0) for line in body_lines)
    secondary_y = tuple(int(top + line.y0) for line in secondary)
    separator_y: list[int] = []
    for line in secondary:
        separator, _blankness = _separator_above(
            ink, int(line.y0), character_height,
        )
        if separator is not None:
            separator_y.append(int(top + separator))

    body_supported = 0
    for entry in legacy:
        _u, canonical_v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        if _legacy_marker_followed_by_body_line(
            int(canonical_v), body_y, character_height,
        ):
            body_supported += 1

    legacy_body_fraction = body_supported / float(max(1, len(legacy)))
    density_ratio = len(legacy) / float(max(1, len(secondary)))
    active = bool(
        len(separator_y) >= 3
        and body_supported >= 7
        and legacy_body_fraction >= 0.60
        and density_ratio >= 1.45
    )
    secondary_center = float(np.median([line.start for line in secondary]))
    return _PolarityEvidence(
        active=active,
        body_line_y0=body_y,
        secondary_line_y0=secondary_y,
        secondary_separator_y=tuple(separator_y),
        baseline=float(baseline),
        secondary_center=secondary_center,
        legacy_count=len(legacy),
        body_supported_legacy=body_supported,
    )


def suppress_inverted_legacy_body_lane(
    image: Image.Image,
    entries: list[Entry],
    geometry: Any,
    settings: AppSettings,
    page_sections: list[Any] | None = None,
) -> list[Entry]:
    """Correct an inverted ordinary lane and emit its proven entry boundaries.

    No OCR/Profile switch is consulted here.  The visual evidence itself is the
    gate.  This matters for the plain ``普通画线`` action: a newly created
    project must not need OCR parser configuration before a strongly repeated
    indented entry lane can be recognized.
    """
    source = normalize_page_rgb(image)
    character_height = max(
        8, int(round(float(getattr(settings, "character_height", 26) or 26)))
    )
    duplicate_tolerance = max(4, round(character_height * 0.50))
    evidence_by_column = {
        column: _column_polarity_evidence(
            source, entries, geometry, settings, column,
        )
        for column in range(len(geometry.column_starts))
    }
    if not any(item.active for item in evidence_by_column.values()):
        return list(entries)

    output: list[Entry] = []
    for entry in entries:
        if str(entry.ocr_source or "") != "ordinary_vb":
            output.append(entry)
            continue
        column = _entry_column(entry, geometry)
        evidence = evidence_by_column.get(column)
        if evidence is None or not evidence.active:
            output.append(entry)
            continue
        _u, canonical_v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        if not _legacy_marker_followed_by_body_line(
            int(canonical_v), evidence.body_line_y0, character_height,
        ):
            output.append(entry)
            continue
        # Suppressed: this is one of the dense flush-left body rows that made
        # the historical ordinary result appear visually inverted.

    # The same evidence that justified suppression now emits the proven
    # secondary entry boundaries.  This makes polarity correction self-contained
    # and independent of the CJK/OCR-specific visual recovery pass that follows.
    for column, evidence in evidence_by_column.items():
        if not evidence.active:
            continue
        for source_y in evidence.secondary_separator_y:
            if not _inside_sections(source_y, page_sections):
                continue
            duplicate = False
            for entry in output:
                if _entry_column(entry, geometry) != column:
                    continue
                _u, existing_v = geometry.source_to_canonical(
                    int(entry.x), int(entry.y)
                )
                if abs(int(existing_v) - int(source_y)) <= duplicate_tolerance:
                    duplicate = True
                    break
            if duplicate:
                continue
            marker_x, _direction = _source_edge(geometry, column, source_y)
            output.append(Entry(
                word="",
                x=int(marker_x),
                y=int(source_y),
                confidence=0.97,
                ocr_source="ordinary_visual_lane",
                issue_type="ORDINARY_INDENTED_ENTRY_LANE_POLARITY",
            ))
    return output
