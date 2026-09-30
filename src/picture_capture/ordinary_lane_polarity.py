from __future__ import annotations

"""Page-level polarity correction for ordinary visual lanes.

Some dictionaries invert the legacy Draw_Auto assumption: dense body text is
flush with the column edge while real subentries (for example ``【...】`` rows)
live on a repeated indented lane. In that layout the faithful VB detector can
fire on nearly every body row. This module keeps the VB detector intact, learns
that page-level polarity from image geometry, suppresses only body-lane VB
markers, and emits the proven secondary-lane separators.

The detector is intentionally OCR/profile independent. Ordinary drawing must be
able to infer a repeated visual lane even before OCR/parser configuration is
complete.
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
    _duplicate,
    _first_ink_lines,
    _otsu,
    _patch_similarity,
    _separator_above,
    _source_edge,
)


@dataclass(slots=True)
class _ColumnObservation:
    column: int
    top: int
    ink: np.ndarray
    lines: list[Any]
    baseline: float | None
    body_lines: list[Any]
    secondary_rows: list[Any]
    secondary_cluster: list[Any]
    secondary_center: float | None

    @property
    def proves_secondary_lane(self) -> bool:
        return bool(
            self.baseline is not None
            and self.secondary_center is not None
            and len(self.secondary_rows) >= 3
            and len(self.secondary_cluster) >= 4
        )


def _entry_column(entry: Entry, geometry: Any) -> int:
    u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
    return min(
        range(len(geometry.column_starts)),
        key=lambda column: abs(int(u) - int(geometry.x_at(column, int(v)))),
    )


def _observe_column(
    source: Image.Image,
    geometry: Any,
    settings: AppSettings,
    column: int,
) -> _ColumnObservation:
    character_height = max(
        8, int(round(float(getattr(settings, "character_height", 26) or 26)))
    )
    top = max(0, int(geometry.top))
    bottom = min(source.height, int(geometry.bottom))
    band = _column_band_gray(source, geometry, column, top, bottom)
    if band.size == 0:
        return _ColumnObservation(column, top, band, [], None, [], [], [], None)

    threshold = _otsu(band)
    ink = band <= threshold
    lines = _first_ink_lines(ink, character_height)
    baseline = _body_lane(lines, ink.shape[1], character_height)
    if baseline is None:
        return _ColumnObservation(column, top, ink, lines, None, [], [], [], None)

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

    best_rows: list[Any] = []
    best_cluster: list[Any] = []
    best_center: float | None = None
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
        center = float(np.median([line.start for line in marker_rows]))
        if center - float(baseline) < character_height * 0.85:
            continue
        score = len(marker_rows) + marker_fraction
        if score > best_score:
            best_rows = marker_rows
            best_cluster = cluster
            best_center = center
            best_score = score

    return _ColumnObservation(
        column=column,
        top=top,
        ink=ink,
        lines=lines,
        baseline=float(baseline),
        body_lines=body_lines,
        secondary_rows=best_rows,
        secondary_cluster=best_cluster,
        secondary_center=best_center,
    )


def _next_visual_line(
    observation: _ColumnObservation,
    marker_v: int,
    character_height: int,
) -> Any | None:
    """Resolve the first normal text line immediately below a VB separator."""
    local_v = int(marker_v) - int(observation.top)
    lower = local_v - max(2, round(character_height * 0.18))
    upper = local_v + max(8, round(character_height * 1.45))
    candidates = [
        line for line in observation.lines
        if lower <= int(line.y0) <= upper
    ]
    if not candidates:
        return None
    # Prefer a line below the separator. If the legacy separator touches the
    # first ink row exactly, allow a tiny negative delta rather than failing the
    # body association altogether.
    return min(
        candidates,
        key=lambda line: (
            0 if int(line.y0) >= local_v - round(character_height * 0.08) else 1,
            abs(int(line.y0) - local_v),
        ),
    )


def _legacy_body_support(
    entries: list[Entry],
    geometry: Any,
    observation: _ColumnObservation,
    character_height: int,
) -> tuple[list[Entry], list[Entry]]:
    legacy = [
        entry for entry in entries
        if str(entry.ocr_source or "") == "ordinary_vb"
        and _entry_column(entry, geometry) == observation.column
    ]
    supported: list[Entry] = []
    if observation.baseline is None:
        return legacy, supported
    body_tolerance = max(5.0, character_height * 0.60)
    for entry in legacy:
        _u, marker_v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        line = _next_visual_line(observation, int(marker_v), character_height)
        if line is None:
            continue
        line_height = int(line.y1) - int(line.y0)
        if line_height > character_height * 1.38:
            # Preserve oversized display heads; the dedicated visual detector
            # handles them independently after polarity correction.
            continue
        if abs(float(line.start) - float(observation.baseline)) <= body_tolerance:
            supported.append(entry)
    return legacy, supported


def _page_proves_inverted_layout(observations: list[_ColumnObservation]) -> bool:
    """One strong column may establish a page-wide dictionary layout rule."""
    proven = [obs for obs in observations if obs.proves_secondary_lane]
    if not proven:
        return False
    # Require at least one genuinely repetitive lane, not a chance cluster.
    return any(
        len(obs.secondary_rows) >= 3
        and len(obs.body_lines) >= 8
        for obs in proven
    )


def _column_inherits_page_polarity(
    legacy_count: int,
    body_supported_count: int,
    observation: _ColumnObservation,
) -> bool:
    """Allow a column with no local subentries to inherit the page polarity.

    This is the key case in multi-column dictionaries: one column can contain
    only the continuation of a large headword while another column contains
    several bracketed subentries. The layout rule belongs to the page/dictionary,
    not to whichever column happens to contain examples on that page.
    """
    if observation.baseline is None or len(observation.body_lines) < 8:
        return False
    if legacy_count < 7 or body_supported_count < 5:
        return False
    fraction = body_supported_count / float(max(1, legacy_count))
    return fraction >= 0.50


def _recover_secondary_rows(
    output: list[Entry],
    geometry: Any,
    settings: AppSettings,
    observation: _ColumnObservation,
    page_sections: list[Any] | None,
) -> list[Entry]:
    if not observation.proves_secondary_lane:
        return output
    character_height = max(
        8, int(round(float(getattr(settings, "character_height", 26) or 26)))
    )
    duplicate_tolerance = max(4, round(character_height * 0.50))
    lane_center = float(observation.secondary_center or 0.0)

    # Once the repeated marker-like lane is proven, nearby numbered variants in
    # the same cluster may join even when their first glyph differs.
    for line in observation.secondary_cluster:
        if abs(float(line.start) - lane_center) > character_height * 0.85:
            continue
        separator, _blankness = _separator_above(
            observation.ink, line.y0, character_height,
        )
        if separator is None:
            continue
        source_y = int(observation.top + int(separator))
        if page_sections and not any(
            int(section.top_v) <= source_y < int(section.bottom_v)
            for section in page_sections
        ):
            continue
        if _duplicate(
            output, geometry, observation.column, source_y, duplicate_tolerance,
        ):
            continue
        marker_x, _direction = _source_edge(
            geometry, observation.column, source_y,
        )
        output.append(Entry(
            word="",
            x=int(marker_x),
            y=source_y,
            confidence=0.96,
            ocr_source="ordinary_visual_lane",
            issue_type="ORDINARY_INDENTED_ENTRY_LANE_POLARITY",
        ))
    return output


def suppress_inverted_legacy_body_lane(
    image: Image.Image,
    entries: list[Entry],
    geometry: Any,
    settings: AppSettings,
    page_sections: list[Any] | None = None,
) -> list[Entry]:
    """Correct dense main-lane VB false positives on inverted dictionary layouts.

    Detection is page-level and OCR/profile independent. A repeated indented
    structural lane in any column can establish the page polarity. Other
    columns may inherit it when their legacy output is densely attached to the
    same dominant body-text lane. Only automatic ``ordinary_vb`` markers are
    suppressed; manual/visual/OCR observations survive.
    """
    source = normalize_page_rgb(image)
    character_height = max(
        8, int(round(float(getattr(settings, "character_height", 26) or 26)))
    )
    observations = [
        _observe_column(source, geometry, settings, column)
        for column in range(len(geometry.column_starts))
    ]
    if not _page_proves_inverted_layout(observations):
        return list(entries)

    suppress_ids: set[int] = set()
    for observation in observations:
        legacy, body_supported = _legacy_body_support(
            entries, geometry, observation, character_height,
        )
        if not _column_inherits_page_polarity(
            len(legacy), len(body_supported), observation,
        ):
            continue
        suppress_ids.update(id(entry) for entry in body_supported)

    output = [
        entry for entry in entries
        if id(entry) not in suppress_ids
    ]

    # Emit the proven secondary-lane rows here as well. The subsequent generic
    # ordinary-visual pass may see the same rows, but its normal de-duplication
    # keeps one marker. Doing this in the polarity pass guarantees that the
    # correction cannot delete body markers without also restoring the entry
    # lane that justified the flip.
    for observation in observations:
        output = _recover_secondary_rows(
            output, geometry, settings, observation, page_sections,
        )
    return output
