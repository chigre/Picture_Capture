from __future__ import annotations

"""Page-level polarity correction for ordinary visual lanes.

Some CJK dictionaries invert the legacy Draw_Auto assumption: ordinary body
text is flush with the column edge while real subentries (for example
``【...】`` rows) live on a repeated indented lane.  In that layout the faithful
VB detector can fire on nearly every body row.  This module does not replace
VB geometry; it detects that *page-level polarity* and suppresses only VB
markers that are demonstrably attached to the dense body lane.  Oversized
heads and the later visual-lane recovery pass remain independent.
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
)


@dataclass(slots=True)
class _PolarityEvidence:
    active: bool
    body_line_y0: tuple[int, ...] = ()
    secondary_line_y0: tuple[int, ...] = ()
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
    """Return body baseline, body lines, and strongest repeated indented lane."""
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
        body_supported >= 7
        and legacy_body_fraction >= 0.60
        and density_ratio >= 1.45
    )
    secondary_center = float(np.median([line.start for line in secondary]))
    return _PolarityEvidence(
        active=active,
        body_line_y0=body_y,
        secondary_line_y0=secondary_y,
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
    """Remove dense false VB body markers when an indented entry lane is proven.

    The correction is intentionally conservative and page-local.  It runs only
    for CJK bracket-capable profiles, requires a repeated visually similar
    secondary lane, and requires the legacy VB output to be implausibly dense on
    the main body lane.  It suppresses only ``ordinary_vb`` rows that can be
    associated with a body line immediately below.  Large display heads are not
    normal body lines and therefore survive; the subsequent ordinary visual pass
    can also recover them independently.
    """
    if not bool(getattr(settings, "profile_cjk_allow_bracketed_headword", True)):
        return list(entries)

    profile_id = str(getattr(settings, "dictionary_profile_id", "") or "").lower()
    ocr_language = str(getattr(settings, "ocr_language", "") or "").lower()
    paddle_language = str(getattr(settings, "paddle_language", "") or "").lower()
    cjk = bool(
        "cjk" in profile_id
        or any(token in ocr_language for token in ("chi_sim", "chi_tra", "chinese", "han"))
        or paddle_language in {"ch", "chi_sim", "chi_tra", "chinese_cht"}
    )
    if not cjk:
        return list(entries)

    source = normalize_page_rgb(image)
    character_height = max(
        8, int(round(float(getattr(settings, "character_height", 26) or 26)))
    )
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
        # A dense flush-left body row on a page with a proven repeated indented
        # structural lane is the inverted-layout failure mode.  Suppress it now;
        # bracketed entries and oversized display heads are recovered by the
        # independent visual pass that follows this function.
    return output
