from __future__ import annotations

"""Column-level topology model for indented dictionary entry layouts.

Some CJK dictionaries use one dominant body-text lane plus several stable
secondary entry lanes.  The latter can differ because plain bracketed entries,
numbered variants and other subentry forms do not always begin at exactly the
same X coordinate.  Treating all of them as one centre forces a wide tolerance
band and makes body/quote indentation much easier to misclassify.

This module therefore learns a *lane family* per column:

* one dominant body lane for definitions, quotations and wrapped prose;
* one or more structurally proven entry sub-lanes to its right;
* oversized display heads as a separate visual class handled upstream.

Once the topology is proven, it is authoritative for normal-height automatic
ordinary candidates.  Candidates attached to neither a proven entry lane nor a
strict right-shifted entry variant are rejected, regardless of which upstream
detector produced them.
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
class EntryLane:
    center: float
    rows: list[Any]
    marker_fraction: float
    separator_fraction: float


@dataclass(slots=True)
class IndentTopology:
    column: int
    top: int
    ink: np.ndarray
    lines: list[Any]
    reference_height: float
    body_center: float
    body_rows: list[Any]
    entry_lanes: list[EntryLane]

    @property
    def entry_rows(self) -> list[Any]:
        rows: list[Any] = []
        seen: set[tuple[int, int, int]] = set()
        for lane in self.entry_lanes:
            for row in lane.rows:
                key = (int(row.y0), int(row.y1), int(row.start))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
        return rows

    @property
    def entry_centers(self) -> tuple[float, ...]:
        return tuple(float(lane.center) for lane in self.entry_lanes)

    @property
    def is_proven(self) -> bool:
        if len(self.body_rows) < 6 or not self.entry_lanes:
            return False
        total_rows = sum(len(lane.rows) for lane in self.entry_lanes)
        if total_rows < 3:
            return False
        reference = float(self.reference_height)
        return all(
            reference * 0.45 <= float(lane.center) - float(self.body_center) <= reference * 4.0
            for lane in self.entry_lanes
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
    # First-ink topology concerns only the left-side text starts. Far-right
    # fragments should not define a semantic lane.
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


def _lane_is_structural(
    *,
    rows: list[Any],
    marker_fraction: float,
    separator_fraction: float,
) -> bool:
    """Require repeated geometry plus at least one independent confirmation.

    Three or more aligned rows are enough when most rows have clean pre-entry
    whitespace and either the leading visual pattern repeats or the population
    is already substantial.  A two-row lane is accepted only when both visual
    marker similarity and separator evidence are very strong; this supports a
    sparse page without opening the gate to arbitrary paragraph indentation.
    """
    count = len(rows)
    if count >= 3:
        return bool(
            separator_fraction >= 0.45
            and (marker_fraction >= 0.34 or count >= 5)
        )
    if count == 2:
        return bool(
            separator_fraction >= 0.80
            and marker_fraction >= 0.60
        )
    return False


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
    clusters = [
        cluster for cluster in _lane_clusters(normal, reference, ink.shape[1])
        if len(cluster) >= 2
    ]
    if not clusters:
        return None

    # Body text normally supplies the largest first-ink mode. Population is the
    # main criterion; a leftward tie-break avoids choosing an indented lane when
    # two modes happen to have equal counts.
    clusters.sort(key=lambda cluster: (-len(cluster), _cluster_center(cluster)))
    body_rows = clusters[0]
    body_center = _cluster_center(body_rows)

    entry_lanes: list[EntryLane] = []
    for cluster in clusters[1:]:
        center = _cluster_center(cluster)
        separation = center - body_center
        if separation < reference * 0.45 or separation > reference * 4.0:
            continue
        marker = _marker_fraction(cluster)
        separator = _separator_fraction(ink, cluster, reference)
        if not _lane_is_structural(
            rows=cluster,
            marker_fraction=marker,
            separator_fraction=separator,
        ):
            continue
        entry_lanes.append(EntryLane(
            center=float(center),
            rows=list(cluster),
            marker_fraction=float(marker),
            separator_fraction=float(separator),
        ))

    if not entry_lanes:
        return None

    # Keep distinct sub-lanes instead of collapsing them into one broad band.
    # Ordering left-to-right makes diagnostics and variant matching stable.
    entry_lanes.sort(key=lambda lane: lane.center)
    topology = IndentTopology(
        column=int(column),
        top=int(top),
        ink=ink,
        lines=lines,
        reference_height=float(reference),
        body_center=float(body_center),
        body_rows=list(body_rows),
        entry_lanes=entry_lanes,
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
    forward = [
        line for line in candidates
        if int(line.y0) >= local_v - round(reference * 0.08)
    ]
    pool = forward or candidates
    return min(pool, key=lambda line: abs(int(line.y0) - local_v))


def _nearest_entry_lane(topology: IndentTopology, start: float) -> EntryLane | None:
    if not topology.entry_lanes:
        return None
    return min(topology.entry_lanes, key=lambda lane: abs(float(start) - lane.center))


def _variant_support(topology: IndentTopology, line: Any) -> bool:
    """Accept a one-off numbered/right-shifted variant only with local support."""
    lane = _nearest_entry_lane(topology, float(line.start))
    if lane is None:
        return False
    reference = float(topology.reference_height)
    shift = float(line.start) - float(lane.center)
    if not (reference * 0.28 <= shift <= reference * 1.35):
        return False
    if _separator_near_next_line(
        topology.ink, int(line.y0), reference,
    ) is None:
        return False
    # The prefix may alter the first glyph substantially, so similarity is a
    # supporting rather than mandatory signal.  Reject only if the candidate is
    # visually unrelated to every proven lane row *and* barely clears the shift
    # threshold, the region most vulnerable to paragraph indentation.
    similarities = [
        _patch_similarity(line.patch, row.patch)
        for row in lane.rows
    ]
    best = max(similarities) if similarities else 0.0
    if shift < reference * 0.50 and best < 0.22:
        return False
    return True


def _line_role(topology: IndentTopology, line: Any) -> str:
    reference = float(topology.reference_height)
    start = float(line.start)
    body_distance = abs(start - float(topology.body_center))
    body_tolerance = max(4.0, reference * 0.38)

    lane = _nearest_entry_lane(topology, start)
    entry_distance = (
        abs(start - float(lane.center)) if lane is not None else float("inf")
    )
    entry_tolerance = max(4.0, reference * 0.38)

    if body_distance <= body_tolerance and body_distance < entry_distance:
        return "body"
    if entry_distance <= entry_tolerance:
        return "entry"
    if _variant_support(topology, line):
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
    """Apply an authoritative per-column body-vs-entry lane-family gate.

    Once a column proves its indentation topology, normal-height automatic
    candidates are kept only when their following line belongs to a proven
    entry sub-lane or to a strictly supported right-shifted variant.  Body-lane
    and unclassified normal lines are suppressed.  Oversized display heads and
    manual markers are never rejected by this gate.
    """
    if not bool(getattr(settings, "profile_cjk_allow_bracketed_headword", True)):
        return list(entries)

    source = normalize_page_rgb(image)
    kind = str(
        getattr(getattr(geometry, "transform", None), "kind", "identity")
        or "identity"
    )
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
        if role in {"entry", "entry_variant"}:
            output.append(entry)
        # Proven topology is authoritative: body and other normal-height lines
        # are both false entry boundaries and are intentionally dropped.

    # Recover every proven sub-lane directly from topology.  This is the crucial
    # difference from the old single-centre model: a page may legitimately have
    # several stable bracket/numbered entry starts.
    for column, topology in topologies.items():
        tolerance = max(4, round(topology.reference_height * 0.34))
        for lane in topology.entry_lanes:
            for line in lane.rows:
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
