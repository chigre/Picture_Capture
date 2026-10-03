from __future__ import annotations

"""OCR-independent dictionary-specific symbol evidence.

Project Profile already lets a user crop real printed entry markers and bracket
openers.  Historically those samples were consumed inside the OCR pipeline and
had to be attached to an OCR text line before they could affect entry detection.
This module promotes the same project-owned samples into an independent evidence
family shared by ordinary, OCR and combined drawing.

The distinction between roles is strict:

* ``entry_marker`` may independently propose an entry boundary after a strong
  template match and page-local lane/block check;
* ``bracket_open`` may confirm an existing detector candidate but never creates
  an entry by itself, because bracket glyphs can legitimately occur in body
  references.

No OCR engine or recognized text is used here.
"""

from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from .image_utils import normalize_page_rgb
from .layout_detection import analysis_ink_mask
from .models import AppSettings, Entry
from .ordinary_visual import _components
from .visual_marker_templates import (
    match_visual_marker_template,
    visual_marker_samples_from_settings,
)


@dataclass(slots=True)
class SymbolMarkerEvidence:
    column_index: int
    role: str
    literal: str
    sample_id: str
    template_score: float
    marker_x: int
    marker_y: int
    boundary_x: int
    boundary_y: int
    lane_x_ratio: float


@dataclass(slots=True)
class SymbolEvidenceResult:
    markers: list[SymbolMarkerEvidence]

    @property
    def entry_markers(self) -> list[SymbolMarkerEvidence]:
        return [item for item in self.markers if item.role == "entry_marker"]

    @property
    def bracket_openers(self) -> list[SymbolMarkerEvidence]:
        return [item for item in self.markers if item.role == "bracket_open"]

    def entry_candidates(self) -> list[Entry]:
        return [
            Entry(
                word="",
                x=int(item.boundary_x),
                y=int(item.boundary_y),
                confidence=float(item.template_score),
                ocr_source="symbol_evidence:entry_marker",
                candidate_id=(
                    f"symbol:{item.sample_id}"
                    if item.sample_id else "symbol:entry_marker"
                ),
                issue_type="SYMBOL_ENTRY_MARKER_RESCUE",
            )
            for item in self.entry_markers
        ]


def _empty() -> SymbolEvidenceResult:
    return SymbolEvidenceResult(markers=[])


def _nearest_layout_line(column: Any, center_y: float, reference: float) -> Any | None:
    lines = list(getattr(column, "lines", []) or [])
    if not lines:
        return None

    def distance(line: Any) -> float:
        y0 = float(getattr(line, "y0", 0))
        y1 = float(getattr(line, "y1", y0))
        if y0 <= center_y <= y1:
            return 0.0
        return min(abs(center_y - y0), abs(center_y - y1))

    line = min(lines, key=distance)
    return line if distance(line) <= max(5.0, reference * 0.85) else None


def _marker_boundary_source(
    layout: Any,
    column: Any,
    line: Any,
    reference: float,
) -> tuple[int, int]:
    # LayoutLine Y is local to body_top.  Keep the same boundary geometry as the
    # Page Design layer so Symbol Evidence does not invent a competing Y system.
    from .dictionary_page_design import _boundary_before

    local = int(_boundary_before(
        list(getattr(column, "lines", []) or []),
        int(getattr(line, "y0", 0)),
        reference,
    ))
    canonical_y = int(layout.body_top) + local
    return layout.transform.canonical_to_source_point(
        int(column.left), canonical_y, layout.source_size,
    )


def _deduplicate_markers(
    markers: list[SymbolMarkerEvidence], reference: float,
) -> list[SymbolMarkerEvidence]:
    output: list[SymbolMarkerEvidence] = []
    for item in sorted(
        markers,
        key=lambda value: (
            value.column_index,
            value.boundary_y,
            -value.template_score,
        ),
    ):
        duplicate = next((
            existing for existing in output
            if existing.column_index == item.column_index
            and existing.role == item.role
            and abs(existing.boundary_y - item.boundary_y) <= reference * 0.30
        ), None)
        if duplicate is None:
            output.append(item)
        elif item.template_score > duplicate.template_score:
            output[output.index(duplicate)] = item
    return output


def _apply_page_local_lane_guard(
    markers: list[SymbolMarkerEvidence],
    settings: AppSettings,
    reference: float,
    threshold: float,
) -> list[SymbolMarkerEvidence]:
    if not bool(getattr(settings, "profile_symbol_lane_required", True)):
        return markers

    tolerance = max(
        4.0,
        reference
        * max(
            20,
            min(120, int(getattr(
                settings, "profile_symbol_lane_tolerance_percent", 50
            ) or 50)),
        )
        / 100.0,
    )
    output: list[SymbolMarkerEvidence] = []
    groups: dict[tuple[int, str], list[SymbolMarkerEvidence]] = {}
    for item in markers:
        groups.setdefault((item.column_index, item.role), []).append(item)

    for (_column, role), group in groups.items():
        if role == "bracket_open":
            # Brackets never rescue by themselves, so retaining a lone strong
            # bracket match for confirmation cannot create a false boundary.
            if len(group) >= 2:
                center = float(np.median([item.marker_x for item in group]))
                output.extend([
                    item for item in group
                    if abs(float(item.marker_x) - center) <= tolerance
                ])
            else:
                output.extend(group)
            continue

        if len(group) >= 2:
            center = float(np.median([item.marker_x for item in group]))
            output.extend([
                item for item in group
                if abs(float(item.marker_x) - center) <= tolerance
            ])
            continue

        # One entry marker on a sparse page is allowed only when the sampled
        # template match itself is exceptionally strong and the marker still
        # lies in the leading structural zone.  This is intentionally stricter
        # than the repeated-lane case.
        only = group[0]
        if (
            only.template_score >= max(0.80, threshold + 0.08)
            and only.lane_x_ratio <= 1.80
        ):
            output.append(only)
    return output


def detect_symbol_evidence(
    image: Image.Image,
    settings: AppSettings,
    layout: Any,
) -> SymbolEvidenceResult:
    """Detect user-sampled entry/bracket markers without OCR.

    Detection is deliberately limited to saved visual samples.  Generic Unicode
    symbol-family heuristics remain available inside the historical OCR stack,
    while this independent route represents *project-specific learned evidence*.
    """
    if not bool(getattr(settings, "profile_symbol_inventory_enabled", True)):
        return _empty()
    if not bool(getattr(settings, "profile_symbol_visual_rescue_enabled", True)):
        return _empty()
    mode = str(getattr(settings, "profile_symbol_template_mode", "combined") or "combined")
    if mode == "off":
        return _empty()

    samples = visual_marker_samples_from_settings(settings)
    if not samples:
        return _empty()
    samples = [
        sample for sample in samples
        if str(sample.get("role") or "") in {"entry_marker", "bracket_open"}
    ]
    if not samples or not getattr(layout, "columns", None):
        return _empty()

    source = normalize_page_rgb(image)
    canonical = layout.transform.canonical_image_for_analysis(source)
    gray = np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8)
    ink = analysis_ink_mask(gray, settings)
    reference = max(6.0, float(getattr(layout, "ordinary_line_height", 0.0) or 0.0))
    threshold = max(
        0.45,
        min(0.95, float(getattr(settings, "profile_symbol_template_threshold", 0.68) or 0.68)),
    )
    top = max(0, min(gray.shape[0] - 1, int(layout.body_top)))
    bottom = max(top + 1, min(gray.shape[0], int(layout.body_bottom)))

    found: list[SymbolMarkerEvidence] = []
    for column in layout.columns:
        left = max(0, min(gray.shape[1] - 1, int(column.left)))
        right = max(left + 1, min(gray.shape[1], int(column.right)))
        zone_width = min(
            right - left,
            max(48, round(reference * 3.2)),
        )
        if zone_width < 8:
            continue
        zone = ink[top:bottom, left:left + zone_width]
        for x0, y0, x1, y1, area in _components(zone):
            width = int(x1 - x0)
            height = int(y1 - y0)
            if area < 3 or width <= 0 or height <= 0:
                continue
            if not (
                reference * 0.14 <= width <= reference * 1.95
                and reference * 0.20 <= height <= reference * 1.95
            ):
                continue
            component = zone[y0:y1, x0:x1]
            try:
                match = match_visual_marker_template(component, samples)
            except ValueError:
                match = None
            if match is None:
                continue
            score = float(match.get("score") or 0.0)
            sample = dict(match.get("sample") or {})
            role = str(sample.get("role") or "")
            required = max(threshold, 0.70) if role == "bracket_open" else threshold
            if score < required:
                continue

            center_local_y = (float(y0) + float(y1)) / 2.0
            line = _nearest_layout_line(column, center_local_y, reference)
            if line is None:
                continue
            boundary_x, boundary_y = _marker_boundary_source(
                layout, column, line, reference,
            )
            marker_canonical_x = left + int(round((x0 + x1) / 2.0))
            marker_canonical_y = top + int(round((y0 + y1) / 2.0))
            marker_x, marker_y = layout.transform.canonical_to_source_point(
                marker_canonical_x,
                marker_canonical_y,
                layout.source_size,
            )
            found.append(SymbolMarkerEvidence(
                column_index=int(column.index),
                role=role,
                literal=str(sample.get("literal") or ""),
                sample_id=str(sample.get("id") or ""),
                template_score=round(score, 5),
                marker_x=int(marker_x),
                marker_y=int(marker_y),
                boundary_x=int(boundary_x),
                boundary_y=int(boundary_y),
                lane_x_ratio=float(x0) / reference,
            ))

    found = _deduplicate_markers(found, reference)
    found = _apply_page_local_lane_guard(found, settings, reference, threshold)
    return SymbolEvidenceResult(markers=found)


def _append_issue(entry: Entry, issue: str) -> Entry:
    parts = [part for part in str(entry.issue_type or "").split(",") if part]
    if issue not in parts:
        parts.append(issue)
    return replace(entry, issue_type=",".join(parts))


def is_symbol_positive_entry(entry: Entry) -> bool:
    return bool(
        str(entry.ocr_source or "").startswith("symbol_evidence:")
        or "SYMBOL_ENTRY_MARKER" in str(entry.issue_type or "")
    )


def _entry_column(layout: Any, entry: Entry) -> int:
    u, _v = layout.transform.source_to_canonical_point(
        int(entry.x), int(entry.y), layout.source_size,
    )
    if not layout.columns:
        return -1
    return int(min(
        layout.columns,
        key=lambda column: abs(float(u) - float(column.left)),
    ).index)


def fuse_symbol_evidence(
    entries: list[Entry],
    evidence: SymbolEvidenceResult,
    understanding: Any,
) -> tuple[list[Entry], dict[str, int]]:
    """Confirm detector rows and rescue unmatched explicit entry markers."""
    markers = list(evidence.markers)
    if not markers:
        return list(entries), {
            "symbol_confirmed": 0,
            "symbol_bracket_confirmed": 0,
            "symbol_rescued": 0,
        }

    reference = max(6.0, float(getattr(understanding, "line_height", 0.0) or 0.0))
    layout = understanding.layout
    output = list(entries)
    used: set[int] = set()
    confirmed = bracket_confirmed = rescued = 0

    # One-to-one nearest-Y pairing keeps repeated symbols from all confirming the
    # same OCR/VB row.
    proposals: list[tuple[float, int, int]] = []
    for marker_index, marker in enumerate(markers):
        for entry_index, entry in enumerate(output):
            if _entry_column(layout, entry) != marker.column_index:
                continue
            delta = abs(int(entry.y) - int(marker.boundary_y))
            if delta <= reference * 0.78:
                proposals.append((float(delta), marker_index, entry_index))

    used_entries: set[int] = set()
    for _delta, marker_index, entry_index in sorted(proposals):
        if marker_index in used or entry_index in used_entries:
            continue
        marker = markers[marker_index]
        issue = (
            "SYMBOL_ENTRY_MARKER_CONFIRMED"
            if marker.role == "entry_marker"
            else "SYMBOL_BRACKET_CONFIRMED"
        )
        output[entry_index] = _append_issue(output[entry_index], issue)
        used.add(marker_index)
        used_entries.add(entry_index)
        if marker.role == "entry_marker":
            confirmed += 1
        else:
            bracket_confirmed += 1

    for marker_index, marker in enumerate(markers):
        if marker_index in used or marker.role != "entry_marker":
            continue
        output.append(Entry(
            word="",
            x=int(marker.boundary_x),
            y=int(marker.boundary_y),
            confidence=float(marker.template_score),
            ocr_source="symbol_evidence:entry_marker",
            candidate_id=(
                f"symbol:{marker.sample_id}"
                if marker.sample_id else "symbol:entry_marker"
            ),
            issue_type="SYMBOL_ENTRY_MARKER_RESCUE",
        ))
        rescued += 1

    return output, {
        "symbol_confirmed": confirmed,
        "symbol_bracket_confirmed": bracket_confirmed,
        "symbol_rescued": rescued,
    }
