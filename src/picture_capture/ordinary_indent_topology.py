from __future__ import annotations

"""Structural topology for normal-height CJK bracket entries.

The abstraction is a visual *block start*, not an isolated indented line. A
normal bracket entry is accepted when three independent page-layout facts agree:

1. a continuous blank boundary exists immediately before the block;
2. the first full-height structural glyph repeats at a stable X lane;
3. that lane is on the semantic entry side selected by the user
   (``词头缩进`` or ``正文缩进``).

Small numeric/superscript prefixes are explicitly ignored when locating the
structural glyph, so ``【词】``, ``1【词】`` and ``12【词】`` belong to the same
entry lane. Oversized display heads are deliberately NOT handled here; they
have their own connected-component signature in ``ordinary_cjk_large_heads``.

Only a left text-start strip is analysed. A tall illustration on the right can
therefore never merge several text rows into one projection run.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image

from .image_utils import normalize_page_rgb
from .models import AppSettings, Entry
from .ordinary_postprocess import _separator_near_next_line
from .ordinary_visual import (
    _column_band_gray,
    _duplicate,
    _entry_column,
    _fill_short_gaps,
    _inside_sections,
    _otsu,
    _patch_similarity,
    _runs,
    _source_edge,
)


_INDENT_SEMANTICS_VERSION = 2


@dataclass(slots=True)
class BlockRow:
    y0: int
    y1: int
    first_start: int
    structural_start: int | None
    patch: np.ndarray
    gap_before: int
    structural_height: int = 0
    max_similarity: float = 0.0

    @property
    def start(self) -> int:
        return int(
            self.structural_start
            if self.structural_start is not None
            else self.first_start
        )

    @property
    def height(self) -> int:
        return int(self.y1) - int(self.y0)


@dataclass(slots=True)
class EntryLane:
    center: float
    tolerance: float
    rows: list[BlockRow]
    marker_fraction: float
    separator_fraction: float


@dataclass(slots=True)
class IndentTopology:
    column: int
    top: int
    ink: np.ndarray
    rows: list[BlockRow]
    reference_height: float
    body_center: float
    body_tolerance: float
    body_rows: list[BlockRow]
    entry_lanes: list[EntryLane]
    indent_type: str = "headword"

    @property
    def lines(self) -> list[BlockRow]:
        return self.rows

    @property
    def entry_rows(self) -> list[BlockRow]:
        result: list[BlockRow] = []
        seen: set[tuple[int, int, int]] = set()
        for lane in self.entry_lanes:
            for row in lane.rows:
                key = (int(row.y0), int(row.y1), int(row.start))
                if key in seen:
                    continue
                seen.add(key)
                result.append(row)
        return result

    @property
    def entry_centers(self) -> tuple[float, ...]:
        return tuple(float(lane.center) for lane in self.entry_lanes)

    @property
    def is_proven(self) -> bool:
        if len(self.body_rows) < 5 or not self.entry_lanes:
            return False
        if sum(len(lane.rows) for lane in self.entry_lanes) < 2:
            return False
        sign = 1.0 if self.indent_type == "headword" else -1.0
        reference = float(self.reference_height)
        return all(
            reference * 0.42
            <= sign * (float(lane.center) - float(self.body_center))
            <= reference * 4.75
            for lane in self.entry_lanes
        )


def _indent_type(settings: AppSettings) -> str:
    # Before semantics v2 the persisted Boolean meant the unrelated fact that
    # bracket words may also occur inside definitions. It must not silently
    # become indentation polarity. Old projects therefore default to headword
    # indentation until the user explicitly saves the new Project Profile choice.
    if int(getattr(settings, "profile_parser_controls_version", 0) or 0) < _INDENT_SEMANTICS_VERSION:
        return "headword"
    return (
        "body"
        if bool(getattr(settings, "profile_cjk_brackets_in_body", False))
        else "headword"
    )


def _character_height(settings: AppSettings) -> int:
    return max(8, int(round(float(getattr(settings, "character_height", 26) or 26))))


def _topology_analysis_width(column_width: int, character_height: int) -> int:
    target = max(
        96,
        round(float(character_height) * 6.25),
        round(float(column_width) * 0.28),
    )
    return max(1, min(int(column_width), int(target)))


def _raw_block_runs(ink: np.ndarray, character_height: int) -> list[tuple[int, int]]:
    """Segment left-strip ink into visual blocks separated by continuous blank Y."""
    if ink.size == 0:
        return []
    width = ink.shape[1]
    active = ink.sum(axis=1) >= max(2, round(width * 0.003))
    active = _fill_short_gaps(active, max(1, round(character_height * 0.10)))
    return [
        (int(y0), int(y1))
        for y0, y1 in _runs(active)
        if character_height * 0.24 <= y1 - y0 <= character_height * 3.65
    ]


def _reference_height(runs: list[tuple[int, int]], fallback: float) -> float:
    heights = np.asarray([y1 - y0 for y0, y1 in runs], dtype=float)
    if heights.size == 0:
        return float(fallback)
    plausible = heights[
        (heights >= float(fallback) * 0.42)
        & (heights <= float(fallback) * 1.45)
    ]
    values = plausible if plausible.size >= 3 else heights[heights <= float(fallback) * 1.60]
    if values.size == 0:
        return float(fallback)
    value = float(np.median(values))
    return max(float(fallback) * 0.55, min(float(fallback) * 1.22, value))


def _component_runs(line: np.ndarray, reference: float) -> list[tuple[int, int, int]]:
    if line.size == 0:
        return []
    active = line.sum(axis=0) >= max(1, round(line.shape[0] * 0.055))
    active = _fill_short_gaps(active, max(1, round(reference * 0.025)))
    result: list[tuple[int, int, int]] = []
    for x0, x1 in _runs(active):
        component = line[:, x0:x1]
        ys = np.flatnonzero(component.any(axis=1))
        if ys.size == 0:
            continue
        result.append((int(x0), int(x1), int(ys[-1] - ys[0] + 1)))
    return result


def _structural_anchor(
    ink: np.ndarray,
    y0: int,
    y1: int,
    reference: float,
) -> tuple[int | None, int, np.ndarray]:
    """Skip small numeric prefixes and anchor on the first full-height glyph."""
    line = ink[int(y0):int(y1)]
    threshold = max(4, round(reference * 0.56))
    structural: tuple[int, int, int] | None = None
    for component in _component_runs(line, reference):
        x0, x1, vertical_span = component
        if vertical_span >= threshold and x1 - x0 >= 2:
            structural = component
            break
    if structural is None:
        return None, 0, np.zeros((0, 0), dtype=bool)

    x0, _x1, vertical_span = structural
    py0 = max(0, int(y0) - round(reference * 0.10))
    py1 = min(ink.shape[0], int(y1) + round(reference * 0.10))
    px0 = max(0, int(x0) - round(reference * 0.05))
    px1 = min(ink.shape[1], int(x0) + round(reference * 0.72))
    return int(x0), int(vertical_span), ink[py0:py1, px0:px1].copy()


def _make_rows(
    ink: np.ndarray,
    runs: list[tuple[int, int]],
    reference: float,
) -> list[BlockRow]:
    result: list[BlockRow] = []
    previous_end = 0
    for y0, y1 in runs:
        line = ink[y0:y1]
        sturdy = line.sum(axis=0) >= max(1, round((y1 - y0) * 0.055))
        xs = np.flatnonzero(sturdy)
        if xs.size == 0:
            previous_end = y1
            continue
        structural_start, structural_height, patch = _structural_anchor(
            ink, y0, y1, reference,
        )
        result.append(BlockRow(
            y0=int(y0),
            y1=int(y1),
            first_start=int(xs[0]),
            structural_start=structural_start,
            patch=patch,
            gap_before=max(0, int(y0) - int(previous_end)),
            structural_height=structural_height,
        ))
        previous_end = y1
    return result


def _cluster_rows(rows: list[BlockRow], tolerance: float) -> list[list[BlockRow]]:
    clusters: list[list[BlockRow]] = []
    for row in sorted(
        [item for item in rows if item.structural_start is not None],
        key=lambda item: item.start,
    ):
        target: list[BlockRow] | None = None
        for cluster in clusters:
            center = float(np.median([item.start for item in cluster]))
            if abs(float(row.start) - center) <= tolerance:
                target = cluster
                break
        if target is None:
            clusters.append([row])
        else:
            target.append(row)
    return clusters


def _cluster_center(cluster: list[BlockRow]) -> float:
    return float(np.median(np.asarray([float(row.start) for row in cluster], dtype=float)))


def _empirical_tolerance(
    rows: list[BlockRow],
    center: float,
    reference: float,
    *,
    minimum_ratio: float = 0.15,
    padding_ratio: float = 0.07,
    maximum_ratio: float = 0.30,
) -> float:
    starts = np.asarray([float(row.start) for row in rows], dtype=float)
    if starts.size == 0:
        return reference * minimum_ratio
    q90 = float(np.quantile(np.abs(starts - float(center)), 0.90))
    return float(min(
        reference * maximum_ratio,
        max(reference * minimum_ratio, q90 + reference * padding_ratio),
    ))


def _separator_supported(ink: np.ndarray, row: BlockRow, reference: float) -> bool:
    return _separator_near_next_line(ink, int(row.y0), reference) is not None


def _separator_fraction(ink: np.ndarray, rows: list[BlockRow], reference: float) -> float:
    if not rows:
        return 0.0
    return sum(_separator_supported(ink, row, reference) for row in rows) / float(len(rows))


def _marker_fraction(rows: list[BlockRow]) -> float:
    usable = [row for row in rows if row.patch.size]
    if len(usable) < 2:
        return 0.0
    matched = 0
    for row in usable:
        similarities = [
            _patch_similarity(row.patch, other.patch)
            for other in usable if other is not row
        ]
        row.max_similarity = max(similarities) if similarities else 0.0
        if row.max_similarity >= 0.34:
            matched += 1
    return matched / float(len(usable))


def _lane_is_structural(
    rows: list[BlockRow],
    marker_fraction: float,
    separator_fraction: float,
) -> bool:
    count = len(rows)
    if count >= 3:
        return bool(separator_fraction >= 0.40 and marker_fraction >= 0.28)
    if count == 2:
        return bool(separator_fraction >= 0.65 and marker_fraction >= 0.48)
    return False


def _observe_column_raw(
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

    analysis_width = _topology_analysis_width(band.shape[1], character_height)
    lane_band = band[:, :analysis_width]
    ink = lane_band <= _otsu(lane_band)
    runs = _raw_block_runs(ink, character_height)
    reference = _reference_height(runs, float(character_height))
    rows = _make_rows(ink, runs, reference)
    normal = [
        row for row in rows
        if reference * 0.48 <= row.height <= reference * 1.48
        and row.structural_start is not None
    ]
    if len(normal) < 4:
        return None

    clusters = [
        cluster for cluster in _cluster_rows(normal, max(3.0, reference * 0.18))
        if len(cluster) >= 2
    ]
    if not clusters:
        return None

    clusters.sort(key=lambda cluster: (-len(cluster), _cluster_center(cluster)))
    body_rows = clusters[0]
    body_center = _cluster_center(body_rows)
    body_tolerance = _empirical_tolerance(
        body_rows,
        body_center,
        reference,
        minimum_ratio=0.16,
        padding_ratio=0.06,
        maximum_ratio=0.34,
    )

    indent_type = _indent_type(settings)
    sign = 1.0 if indent_type == "headword" else -1.0
    entry_lanes: list[EntryLane] = []
    for cluster in clusters[1:]:
        center = _cluster_center(cluster)
        signed_separation = sign * (center - body_center)
        if not (reference * 0.42 <= signed_separation <= reference * 4.75):
            continue
        marker = _marker_fraction(cluster)
        separator = _separator_fraction(ink, cluster, reference)
        if not _lane_is_structural(cluster, marker, separator):
            continue
        entry_lanes.append(EntryLane(
            center=float(center),
            tolerance=_empirical_tolerance(cluster, center, reference),
            rows=list(cluster),
            marker_fraction=float(marker),
            separator_fraction=float(separator),
        ))
    entry_lanes.sort(key=lambda lane: lane.center)

    return IndentTopology(
        column=int(column),
        top=int(top),
        ink=ink,
        rows=rows,
        reference_height=float(reference),
        body_center=float(body_center),
        body_tolerance=float(body_tolerance),
        body_rows=list(body_rows),
        entry_lanes=entry_lanes,
        indent_type=indent_type,
    )


def _observe_column(
    source: Image.Image,
    geometry: Any,
    settings: AppSettings,
    column: int,
) -> IndentTopology | None:
    topology = _observe_column_raw(source, geometry, settings, column)
    return topology if topology is not None and topology.is_proven else None


def _prototype_similarity(row: BlockRow, prototypes: list[np.ndarray]) -> float:
    if not row.patch.size or not prototypes:
        return 0.0
    values = [_patch_similarity(row.patch, patch) for patch in prototypes if patch.size]
    return max(values) if values else 0.0


def _seed_sparse_columns(topologies: dict[int, IndentTopology]) -> None:
    proven = [topology for topology in topologies.values() if topology.is_proven]
    if not proven:
        return

    offsets: list[float] = []
    prototypes: list[np.ndarray] = []
    for topology in proven:
        sign = 1.0 if topology.indent_type == "headword" else -1.0
        for lane in topology.entry_lanes:
            offsets.append(
                sign * (float(lane.center) - float(topology.body_center))
                / max(1.0, float(topology.reference_height))
            )
            prototypes.extend(row.patch for row in lane.rows if row.patch.size)
    if not offsets or not prototypes:
        return

    normalized_offset = float(np.median(np.asarray(offsets, dtype=float)))
    for topology in topologies.values():
        if topology.is_proven:
            continue
        sign = 1.0 if topology.indent_type == "headword" else -1.0
        predicted = (
            float(topology.body_center)
            + sign * normalized_offset * float(topology.reference_height)
        )
        candidates = [
            row for row in topology.rows
            if topology.reference_height * 0.48 <= row.height <= topology.reference_height * 1.48
            and row.structural_start is not None
            and abs(float(row.start) - predicted) <= topology.reference_height * 0.34
            and _separator_supported(topology.ink, row, topology.reference_height)
            and _prototype_similarity(row, prototypes) >= 0.26
        ]
        if not candidates:
            continue
        center = float(np.median(np.asarray([row.start for row in candidates], dtype=float)))
        topology.entry_lanes = [EntryLane(
            center=center,
            tolerance=_empirical_tolerance(candidates, center, topology.reference_height),
            rows=candidates,
            marker_fraction=1.0,
            separator_fraction=1.0,
        )]


def _nearest_row(topology: IndentTopology, marker_v: int) -> BlockRow | None:
    local_v = int(marker_v) - int(topology.top)
    reference = float(topology.reference_height)
    candidates = [
        row for row in topology.rows
        if local_v - reference * 0.14 <= int(row.y0) <= local_v + reference * 1.75
    ]
    if not candidates:
        return None
    forward = [row for row in candidates if int(row.y0) >= local_v - reference * 0.08]
    pool = forward or candidates
    return min(pool, key=lambda row: abs(int(row.y0) - local_v))


def _nearest_entry_lane(topology: IndentTopology, start: float) -> EntryLane | None:
    if not topology.entry_lanes:
        return None
    return min(topology.entry_lanes, key=lambda lane: abs(float(start) - lane.center))


def _row_role(topology: IndentTopology, row: BlockRow) -> str:
    if row.structural_start is None:
        return "other"
    start = float(row.start)
    body_distance = abs(start - float(topology.body_center))
    lane = _nearest_entry_lane(topology, start)
    entry_distance = abs(start - lane.center) if lane is not None else float("inf")
    if lane is not None and entry_distance <= float(lane.tolerance):
        return "entry"
    if body_distance <= float(topology.body_tolerance):
        return "body"
    return "other"


def _is_automatic_ordinary(entry: Entry) -> bool:
    if bool(getattr(entry, "manually_selected", False)):
        return False
    source = str(getattr(entry, "ocr_source", "") or "")
    return source == "" or source.startswith("ordinary")


def _append_boundary(
    output: list[Entry],
    topology: IndentTopology,
    geometry: Any,
    page_sections: list[Any] | None,
    row: BlockRow,
) -> None:
    separator = _separator_near_next_line(
        topology.ink,
        int(row.y0),
        topology.reference_height,
    )
    if separator is None:
        return
    source_y = int(topology.top) + int(separator)
    if not _inside_sections(source_y, page_sections):
        return
    tolerance = max(4, round(topology.reference_height * 0.26))
    if _duplicate(output, geometry, topology.column, source_y, tolerance):
        return
    marker_x, _direction = _source_edge(geometry, topology.column, source_y)
    output.append(Entry(
        word="",
        x=int(marker_x),
        y=int(source_y),
        confidence=0.98,
        ocr_source="ordinary_visual_lane",
        issue_type="ORDINARY_BLOCK_BRACKET_ENTRY",
        ocr_visual_run_height=float(row.height),
        ocr_line_height_reference=float(topology.reference_height),
    ))


def finalize_indented_topology(
    image: Image.Image,
    entries: list[Entry],
    geometry: Any,
    settings: AppSettings,
    page_sections: list[Any] | None = None,
) -> list[Entry]:
    """Suppress body candidates and proactively publish proven bracket block starts."""
    source = normalize_page_rgb(image)
    kind = str(
        getattr(getattr(geometry, "transform", None), "kind", "identity")
        or "identity"
    )
    if kind not in {"identity", "mirror_x"}:
        return list(entries)

    raw = {
        column: topology
        for column in range(len(geometry.column_starts))
        if (topology := _observe_column_raw(source, geometry, settings, column)) is not None
    }
    if not raw:
        return list(entries)
    _seed_sparse_columns(raw)

    output: list[Entry] = []
    for entry in entries:
        if not _is_automatic_ordinary(entry):
            output.append(entry)
            continue
        column = _entry_column(entry, geometry)
        topology = raw.get(column)
        if topology is None or not topology.is_proven:
            output.append(entry)
            continue
        _u, marker_v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        row = _nearest_row(topology, int(marker_v))
        if row is None:
            continue
        if _row_role(topology, row) == "entry":
            output.append(entry)

    if bool(getattr(settings, "profile_cjk_allow_bracketed_headword", True)):
        for topology in raw.values():
            if not topology.is_proven:
                continue
            for lane in topology.entry_lanes:
                for row in lane.rows:
                    _append_boundary(output, topology, geometry, page_sections, row)

    return output
