from __future__ import annotations

"""Column-level topology model for indented dictionary entry layouts.

Some dictionaries use two stable first-ink lanes inside one text column:

* a dominant left/body lane for definitions, quotations and wrapped prose;
* a secondary right/entry lane for bracketed subentries such as ``【...】``.

The important signal is therefore not whether one isolated row happens to have
blank space above it, but which *lane* the following text line belongs to.  This
module learns those lanes from the page image itself and acts as the final gate
for automatic ordinary-mode candidates.  Oversized display heads remain a
separate visual class and are never rejected merely for living outside the
secondary lane.

The model is deliberately per-column.  A page may contain columns with different
local mixtures of body text and entry rows, so no page-wide polarity is imposed.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image

from .image_utils import normalize_page_rgb
from .models import AppSettings, Entry
from .ordinary_postprocess import _separator_near_next_line
from .ordinary_visual import (
    _cluster_lines,
    _column_band_gray,
    _duplicate,
    _entry_column,
    _first_ink_lines,
    _inside_sections,
    _otsu,
    _patch_similarity,
    _source_edge,
)


@dataclass(slots=True)
class IndentTopology:
    column: int
    top: int
    ink: np.ndarray
    lines: list[Any]
    reference_height: float
    body_center: float
    body_rows: list[Any]
    entry_center: float
    entry_rows: list[Any]
    lane_separation: float
    marker_fraction: float
    separator_fraction: float

    @property
    def is_proven(self) -> bool:
        # The absolute row counts prevent a chance pair of aligned prose lines
        # from defining a semantic lane.  The two softer evidence channels are
        # alternatives: a repeated leading marker pattern, or enough rows that
        # the geometric mode is already difficult to explain by chance.
        return bool(
            len(self.body_rows) >= 6
            and len(self.entry_rows) >= 3
            and self.lane_separation >= self.reference_height * 0.45
            and self.lane_separation <= self.reference_height * 4.0
            and self.separator_fraction >= 0.45
            and (
                self.marker_fraction >= 0.34
                or len(self.entry_rows) >= 5
            )
        )


def _character_height(settings: AppSettings) -> int:
    return max(8, int(round(float(getattr(settings, "character_height", 26) or 26))))


def _reference_height(lines: list[Any], fallback: float) -> float:
    heights = [
        int(line.y1) - int(line.y0)
        for line in lines
        if int(line.y1) > int(line.y0)
    ]
    if not heights:
        return float(fallback)
    value = float(np.median(np.asarray(heights, dtype=float)))
    return max(6.0, min(float(fallback) * 1.35, value))


def _normal_lines(lines: list[Any], reference: float) -> list[Any]:
    return [
        line for line in lines
        if reference * 0.55 <= int(line.y1) - int(line.y0) <= reference * 1.55
    ]


def _lane_clusters(lines: list[Any], reference: float, width: int) -> list[list[Any]]:
    # Lane topology only concerns the left-side text starts.  Far-right starts
    # are usually hanging fragments, examples or table material and should not
    # define a first-ink mode.
    maximum = min(float(width) * 0.32, reference * 6.0)
    candidates = [line for line in lines if float(line.start) <= maximum]
    return _cluster_lines(candidates, max(3.0, reference * 0.28))


def _cluster_center(cluster: list[Any]) -> float:
    return float(np.median(np.asarray([float(line.start) for line in cluster], dtype=float)))


def _separator_fraction(ink: np.ndarray, rows: list[Any], reference: float) -> float:
    if not rows:
        return 0.0
    supported = 0
    for line in rows:
        if _separator_near_next_line(ink, int(line.y0), reference) is not None:
            supported += 1
    return supported / float(len(rows))


def _marker_fraction(rows: list[Any]) -> float:
    if len(rows) < 2:
        return 0.0
    matched = 0
    for line in rows:
        similarities = [
            _patch_similarity(line.patch, other.patch)
            for other in rows if other is not line
        ]
        line.max_similarity = max(similarities) if similarities else 0.0
        if line.max_similarity >= 0.42:
            matched += 1
    return matched / float(len(rows))


def _observe_column(
    source: Image.Image,
    geometry: Any,
    settings: AppSettings,
    column: int,
) -> IndentTopology | None:
    character_height = _character_height(settings)
    top = max(0, int(geometry.top))
    bottom = min(source.height, int(geometry.bottom))
    band = _column_band_gray(source, geometry, column, top, bottom)
    if band.size == 0:
        return None
    ink = band <= _otsu(band)
    lines = _first_ink_lines(ink, character_height)
    reference = _reference_height(lines, float(character_height))
    normal = _normal_lines(lines, reference)
    clusters = [cluster for cluster in _lane_clusters(normal, reference, ink.shape[1]) if len(cluster) >= 2]
    if not clusters:
        return None

    # The body lane is the dominant first-ink mode, not necessarily the literal
    # column edge.  Prefer population first, then the more leftward center for a
    # deterministic tie break.
    clusters.sort(key=lambda cluster: (-len(cluster), _cluster_center(cluster)))
    body_rows = clusters[0]
    body_center = _cluster_center(body_rows)

    entry_candidates: list[tuple[float, list[Any], float, float]] = []
    for cluster in clusters[1:]:
        center = _cluster_center(cluster)
        separation = center - body_center
        if separation < reference * 0.45 or separation > reference * 4.0:
            continue
        marker = _marker_fraction(cluster)
        separator = _separator_fraction(ink, cluster, reference)
        # Population is the strongest term; marker repetition and clean
        # pre-entry whitespace are independent confirmation channels.
        score = float(len(cluster)) + marker * 2.0 + separator * 1.5
        entry_candidates.append((score, cluster, marker, separator))

    if not entry_candidates:
        return None
    entry_candidates.sort(key=lambda item: item[0], reverse=True)
    _score, entry_rows, marker_fraction, separator_fraction = entry_candidates[0]
    entry_center = _cluster_center(entry_rows)

    topology = IndentTopology(
        column=int(column),
        top=int(top),
        ink=ink,
        lines=lines,
        reference_height=float(reference),
        body_center=float(body_center),
        body_rows=list(body_rows),
        entry_center=float(entry_center),
        entry_rows=list(entry_rows),
        lane_separation=float(entry_center - body_center),
        marker_fraction=float(marker_fraction),
        separator_fraction=float(separator_fraction),
    )
    return topology if topology.is_proven else None


def _next_line(topology: IndentTopology, marker_v: int) -> Any | None:
    local_v = int(marker_v) - int(topology.top)
    reference = float(topology.reference_height)
    lower = local_v - max(2, round(reference * 0.12))
    upper = local_v + max(10, round(reference * 1.75))
    candidates = [line for line in topology.lines if lower <= int(line.y0) <= upper]
    if not candidates:
        return None
    forward = [line for line in candidates if int(line.y0) >= local_v - round(reference * 0.08)]
    pool = forward or candidates
    return min(pool, key=lambda line: abs(int(line.y0) - local_v))


def _line_role(topology: IndentTopology, line: Any) -> str:
    reference = float(topology.reference_height)
    start = float(line.start)
    body_distance = abs(start - float(topology.body_center))
    entry_distance = abs(start - float(topology.entry_center))
    body_tolerance = max(4.0, reference * 0.38)
    entry_tolerance = max(4.0, reference * 0.48)
    if body_distance <= body_tolerance and body_distance < entry_distance:
        return "body"
    if entry_distance <= entry_tolerance:
        return "entry"
    # A superscript/number prefix may move first ink to the right of the proven
    # entry lane.  It may not move left into the body lane.
    shift = start - float(topology.entry_center)
    if reference * 0.30 <= shift <= reference * 1.50:
        return "entry_variant"
    return "other"


def _is_automatic_ordinary(entry: Entry) -> bool:
    if bool(getattr(entry, "manually_selected", False)):
        return False
    source = str(getattr(entry, "ocr_source", "") or "")
    return source == "" or source.startswith("ordinary")


def _is_display_head(entry: Entry) -> bool:
    source = str(getattr(entry, "ocr_source", "") or "")
    return bool(
        source == "ordinary_visual_head"
        or getattr(entry, "ocr_oversized_cjk", False)
        or "OVERSIZED_HEAD" in str(getattr(entry, "issue_type", "") or "")
    )


def finalize_indented_topology(
    image: Image.Image,
    entries: list[Entry],
    geometry: Any,
    settings: AppSettings,
    page_sections: list[Any] | None = None,
) -> list[Entry]:
    """Apply an authoritative per-column body-vs-entry lane gate.

    Once a column proves two stable first-ink lanes, normal-height automatic
    candidates attached to the body lane are false entry boundaries regardless
    of which upstream detector produced them.  Rows on the entry lane are kept
    or recovered.  Ambiguous rows and oversized display heads are preserved.
    """
    if not bool(getattr(settings, "profile_cjk_allow_bracketed_headword", True)):
        return list(entries)

    source = normalize_page_rgb(image)
    kind = str(getattr(getattr(geometry, "transform", None), "kind", "identity") or "identity")
    if kind not in {"identity", "mirror_x"}:
        return list(entries)

    topologies = {
        column: topology
        for column in range(len(geometry.column_starts))
        if (topology := _observe_column(source, geometry, settings, column)) is not None
    }
    if not topologies:
        return list(entries)

    output: list[Entry] = []
    for entry in entries:
        if not _is_automatic_ordinary(entry) or _is_display_head(entry):
            output.append(entry)
            continue
        column = _entry_column(entry, geometry)
        topology = topologies.get(column)
        if topology is None:
            output.append(entry)
            continue
        _u, marker_v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        line = _next_line(topology, int(marker_v))
        if line is None:
            output.append(entry)
            continue
        line_height = int(line.y1) - int(line.y0)
        if line_height >= topology.reference_height * 1.48:
            # Main display heads are a third visual class, not body prose.
            output.append(entry)
            continue
        role = _line_role(topology, line)
        if role == "body":
            continue
        output.append(entry)

    # Recover the normal-height entry lane directly from the learned topology.
    # This replaces the old secondary pass that tried to infer entryhood from a
    # single row's indentation and whitespace in isolation.
    for column, topology in topologies.items():
        tolerance = max(4, round(topology.reference_height * 0.45))
        for line in topology.entry_rows:
            separator = _separator_near_next_line(
                topology.ink, int(line.y0), topology.reference_height,
            )
            if separator is None:
                continue
            source_y = int(topology.top) + int(separator)
            if not _inside_sections(source_y, page_sections):
                continue
            if _duplicate(output, geometry, column, source_y, tolerance):
                continue
            marker_x, _direction = _source_edge(geometry, column, source_y)
            output.append(Entry(
                word="",
                x=int(marker_x),
                y=int(source_y),
                confidence=0.97,
                ocr_source="ordinary_visual_lane",
                issue_type="ORDINARY_INDENT_TOPOLOGY_ENTRY",
            ))

    return output
