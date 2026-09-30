from __future__ import annotations

"""OCR-free dictionary page design inference and entry-boundary drawing.

The detector in this module starts from the way a dictionary page is *designed*,
not from isolated headword candidates.  The page is first reduced to a stable
layout model:

* canonical reading direction (supplied by Project Profile);
* physical header/footer/side exclusions;
* body rectangle and true column geometry;
* ordinary line/character scale;
* per-column indentation modes;
* explicit user semantics: headword-indent vs body-indent;
* optional display-size (oversized) headwords.

Entry boundaries are then consequences of that model.  A normal entry is a
normal-size block whose structural anchor belongs to an entry indentation mode.
A small numeric/superscript prefix may precede that anchor without changing the
mode.  An oversized display head is a separate typographic size level.  Both are
anchored to the whitespace immediately before the visual block.

No text recognition or language model is used here.  Repeated visual shape is
only supporting evidence for a stable layout mode; it is never required to know
which character or bracket was printed.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .image_utils import normalize_page_rgb
from .layout_detection import _projection_layout_estimate, analysis_ink_mask
from .layout_transform import LayoutTransform
from .models import AppSettings, Entry
from .ordinary_visual import _components, _fill_short_gaps, _patch_similarity, _runs
from .profile_indent_ui import indent_type_label
from .profile_semantics import effective_page_settings, page_template_analysis_image


@dataclass(slots=True)
class LayoutLine:
    column: int
    y0: int
    y1: int
    first_x: int
    anchor_x: int | None
    anchor_height: int
    gap_before: int
    patch: np.ndarray
    has_small_prefix: bool = False
    role: str = "unknown"  # body / entry / unknown

    @property
    def height(self) -> int:
        return int(self.y1) - int(self.y0)


@dataclass(slots=True)
class IndentMode:
    center: float
    tolerance: float
    lines: list[LayoutLine] = field(default_factory=list)
    shape_consensus: float = 0.0
    role: str = "unknown"

    @property
    def support(self) -> int:
        return len(self.lines)


@dataclass(slots=True)
class ColumnDesign:
    index: int
    left: int
    right: int
    gutter_after: int
    lines: list[LayoutLine] = field(default_factory=list)
    indent_modes: list[IndentMode] = field(default_factory=list)
    body_mode: IndentMode | None = None
    entry_modes: list[IndentMode] = field(default_factory=list)

    @property
    def width(self) -> int:
        return max(1, int(self.right) - int(self.left))


@dataclass(slots=True)
class DisplayHead:
    column: int
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return int(self.x1) - int(self.x0)

    @property
    def height(self) -> int:
        return int(self.y1) - int(self.y0)


@dataclass(slots=True)
class DictionaryPageLayout:
    transform: LayoutTransform
    source_size: tuple[int, int]
    canonical_size: tuple[int, int]
    body_top: int
    body_bottom: int
    columns: list[ColumnDesign]
    ordinary_line_height: float
    ordinary_line_pitch: float
    ordinary_char_width: float
    ordinary_char_height: float
    indent_type: str  # headword / body
    display_heads: list[DisplayHead] = field(default_factory=list)
    display_head_width: float = 0.0
    display_head_height: float = 0.0
    reliable: bool = False
    reason: str = ""

    @property
    def has_display_heads(self) -> bool:
        return bool(self.display_heads)


@dataclass(slots=True)
class LayoutDetectionResult:
    entries: list[Entry]
    layout: DictionaryPageLayout


def _indent_type(settings: AppSettings) -> str:
    return "body" if indent_type_label(settings) == "正文缩进" else "headword"


def _canonical_analysis_page(
    image: Image.Image,
    settings: AppSettings,
    page_index: int,
) -> tuple[Image.Image, Image.Image, LayoutTransform, AppSettings]:
    source = normalize_page_rgb(image)
    effective = effective_page_settings(settings, source.size, page_index)
    template = page_template_analysis_image(source, settings, page_index)
    transform = LayoutTransform(str(getattr(settings, "layout_transform", "identity") or "identity"))
    canonical = transform.canonical_image_for_analysis(template)
    return source, canonical, transform, effective


def _projection_geometry(
    canonical: Image.Image,
    effective: AppSettings,
) -> tuple[int, int, list[int], list[int], list[int]]:
    """Recover body/column design with no text recognition.

    The projection estimator already treats a persistent vertical rule as an
    object *inside* a gutter.  Column distance therefore comes from text regions
    and persistent whitespace, not from the rule width itself.
    """
    estimate = _projection_layout_estimate(canonical, effective)
    top = max(0, min(canonical.height - 1, int(estimate.start_y)))
    bottom = max(top + 1, min(canonical.height, int(estimate.bottom_y)))
    starts = list(estimate.column_starts)
    rights = list(estimate.column_rights)
    if not starts:
        starts = [int(estimate.manual_x) + i * (int(estimate.column_width) + int(estimate.gutter))
                  for i in range(max(1, int(estimate.columns)))]
    if len(rights) != len(starts):
        rights = [min(canonical.width, int(x) + int(estimate.column_width)) for x in starts]
    gutters: list[int] = []
    for index in range(len(starts)):
        if index + 1 < len(starts):
            gutters.append(max(0, int(starts[index + 1]) - int(rights[index])))
        else:
            gutters.append(0)
    return top, bottom, [int(x) for x in starts], [int(x) for x in rights], gutters


def _leading_strip_width(column_width: int, seed_height: float) -> int:
    # Enough width to contain several ordinary CJK cells and all normal indent
    # levels, while ignoring illustrations/tables in the far half of a column.
    target = max(round(column_width * 0.42), round(seed_height * 7.0), 96)
    return max(24, min(int(column_width), int(target)))


def _line_runs(ink: np.ndarray, seed_height: float) -> list[tuple[int, int]]:
    if ink.size == 0:
        return []
    width = ink.shape[1]
    active = ink.sum(axis=1) >= max(2, round(width * 0.003))
    active = _fill_short_gaps(active, max(1, round(seed_height * 0.09)))
    return [
        (int(y0), int(y1))
        for y0, y1 in _runs(active)
        if seed_height * 0.26 <= y1 - y0 <= seed_height * 1.90
    ]


def _robust_normal_height(
    runs_by_column: list[list[tuple[int, int]]],
    fallback: float,
) -> float:
    heights = np.asarray(
        [float(y1 - y0) for runs in runs_by_column for y0, y1 in runs],
        dtype=float,
    )
    if heights.size == 0:
        return max(6.0, float(fallback))
    seed = max(6.0, float(fallback))
    plausible = heights[(heights >= seed * 0.45) & (heights <= seed * 1.55)]
    values = plausible if plausible.size >= 5 else heights
    center = float(np.median(values))
    deviations = np.abs(values - center)
    mad = float(np.median(deviations)) if deviations.size else 0.0
    if mad > 0:
        kept = values[deviations <= max(2.0, 3.5 * mad)]
        if kept.size:
            center = float(np.median(kept))
    return max(seed * 0.55, min(seed * 1.35, center))


def _component_runs(line: np.ndarray, reference: float) -> list[tuple[int, int, int]]:
    if line.size == 0:
        return []
    active = line.sum(axis=0) >= max(1, round(line.shape[0] * 0.055))
    active = _fill_short_gaps(active, max(1, round(reference * 0.025)))
    result: list[tuple[int, int, int]] = []
    for x0, x1 in _runs(active):
        component = line[:, x0:x1]
        ys = np.flatnonzero(component.any(axis=1))
        if ys.size:
            result.append((int(x0), int(x1), int(ys[-1] - ys[0] + 1)))
    return result


def _line_feature(
    column: int,
    ink: np.ndarray,
    y0: int,
    y1: int,
    reference: float,
    previous_end: int,
) -> LayoutLine | None:
    line = ink[int(y0):int(y1)]
    sturdy = line.sum(axis=0) >= max(1, round(max(1, y1 - y0) * 0.055))
    starts = np.flatnonzero(sturdy)
    if starts.size == 0:
        return None
    first_x = int(starts[0])
    threshold = max(4, round(reference * 0.56))
    anchors = [part for part in _component_runs(line, reference)
               if part[2] >= threshold and part[1] - part[0] >= 2]
    anchor_x: int | None = int(anchors[0][0]) if anchors else None
    anchor_height = int(anchors[0][2]) if anchors else 0
    has_small_prefix = bool(anchor_x is not None and first_x < anchor_x - reference * 0.12)
    if anchor_x is None:
        patch = np.zeros((0, 0), dtype=bool)
    else:
        py0 = max(0, int(y0) - round(reference * 0.10))
        py1 = min(ink.shape[0], int(y1) + round(reference * 0.10))
        px0 = max(0, int(anchor_x) - round(reference * 0.05))
        px1 = min(ink.shape[1], int(anchor_x) + round(reference * 0.78))
        patch = ink[py0:py1, px0:px1].copy()
    return LayoutLine(
        column=int(column), y0=int(y0), y1=int(y1),
        first_x=first_x, anchor_x=anchor_x, anchor_height=anchor_height,
        gap_before=max(0, int(y0) - int(previous_end)), patch=patch,
        has_small_prefix=has_small_prefix,
    )


def _cluster_indent_modes(lines: list[LayoutLine], reference: float) -> list[IndentMode]:
    usable = [line for line in lines if line.anchor_x is not None]
    if not usable:
        return []
    tolerance = max(3.0, reference * 0.24)
    clusters: list[list[LayoutLine]] = []
    for line in sorted(usable, key=lambda item: int(item.anchor_x or 0)):
        target: list[LayoutLine] | None = None
        for cluster in clusters:
            center = float(np.median([float(item.anchor_x or 0) for item in cluster]))
            if abs(float(line.anchor_x or 0) - center) <= tolerance:
                target = cluster
                break
        if target is None:
            clusters.append([line])
        else:
            target.append(line)

    modes: list[IndentMode] = []
    for cluster in clusters:
        center = float(np.median([float(item.anchor_x or 0) for item in cluster]))
        deviations = np.asarray([abs(float(item.anchor_x or 0) - center) for item in cluster])
        q90 = float(np.quantile(deviations, 0.90)) if deviations.size else 0.0
        mode_tolerance = max(reference * 0.14, min(reference * 0.34, q90 + reference * 0.08))
        modes.append(IndentMode(
            center=center,
            tolerance=float(mode_tolerance),
            lines=list(cluster),
            shape_consensus=_shape_consensus(cluster),
        ))
    return sorted(modes, key=lambda mode: mode.center)


def _shape_consensus(lines: list[LayoutLine]) -> float:
    usable = [line for line in lines if line.patch.size]
    if len(usable) < 2:
        return 0.0
    best = 0.0
    for prototype in usable:
        matches = sum(
            _patch_similarity(prototype.patch, line.patch) >= 0.52
            for line in usable
        )
        best = max(best, matches / float(len(usable)))
    return float(best)


def _choose_semantic_modes(
    column: ColumnDesign,
    indent_type: str,
    reference: float,
) -> None:
    modes = column.indent_modes
    if not modes:
        return
    normal_count = max(1, sum(mode.support for mode in modes))
    minimum_support = max(3, round(normal_count * 0.12))
    stable = [mode for mode in modes if mode.support >= minimum_support]
    if not stable:
        stable = [max(modes, key=lambda item: item.support)]

    # User semantics resolve the ambiguity that image statistics cannot: in a
    # headword-indent dictionary the body occupies the least-indented stable
    # lane; in a body-indent dictionary it occupies the most-indented lane.
    body = min(stable, key=lambda item: item.center) if indent_type == "headword" else max(stable, key=lambda item: item.center)
    body.role = "body"
    column.body_mode = body

    sign = 1.0 if indent_type == "headword" else -1.0
    entries: list[IndentMode] = []
    for mode in modes:
        if mode is body:
            continue
        separation = sign * (float(mode.center) - float(body.center))
        if not (reference * 0.42 <= separation <= reference * 5.0):
            continue
        # A repeated indent is already page-design evidence. Repeated leading
        # shape (e.g. the same bracket) and a small prefix are supporting cues,
        # not semantic requirements.
        if mode.support >= 2:
            mode.role = "entry"
            entries.append(mode)
    column.entry_modes = entries


def _ordinary_pitch(columns: list[ColumnDesign], reference: float) -> float:
    steps: list[float] = []
    for column in columns:
        ys = sorted(line.y0 for line in column.lines if reference * 0.55 <= line.height <= reference * 1.45)
        steps.extend(float(b - a) for a, b in zip(ys, ys[1:]) if reference * 0.75 <= b - a <= reference * 2.2)
    return float(np.median(np.asarray(steps, dtype=float))) if steps else float(reference * 1.25)


def _ordinary_char_width(columns: list[ColumnDesign], reference: float) -> float:
    widths: list[float] = []
    for column in columns:
        for line in column.lines[:24]:
            if line.anchor_x is None:
                continue
            # The leading full-height structure is a useful character-cell proxy
            # after small prefixes have been skipped. CJK/boxed glyphs that split
            # into strokes are rejected by the broad plausibility window below.
            local = max(1.0, float(line.anchor_height))
            if reference * 0.50 <= local <= reference * 1.35:
                widths.append(local)
    if len(widths) >= 5:
        return float(np.median(np.asarray(widths, dtype=float)))
    return float(reference)


def _dilated_components(ink: np.ndarray, reference: float) -> list[tuple[int, int, int, int, int]]:
    if ink.size == 0:
        return []
    radius = max(1, round(reference * 0.035))
    size = max(3, radius * 2 + 1)
    if size % 2 == 0:
        size += 1
    binary = Image.fromarray((ink.astype(np.uint8) * 255), mode="L")
    try:
        joined = np.asarray(binary.filter(ImageFilter.MaxFilter(size=size)), dtype=np.uint8) > 0
    finally:
        binary.close()
    return _components(joined)


def _display_heads(
    column: ColumnDesign,
    column_ink: np.ndarray,
    reference: float,
    indent_type: str,
) -> list[DisplayHead]:
    body = column.body_mode
    if body is None:
        return []
    sign = 1.0 if indent_type == "headword" else -1.0
    result: list[DisplayHead] = []
    minimum_area = max(6, round(reference * reference * 0.12))
    for x0, y0, x1, y1, area in _dilated_components(column_ink, reference):
        width = int(x1) - int(x0)
        height = int(y1) - int(y0)
        if area < minimum_area:
            continue
        if not (reference * 1.35 <= height <= reference * 3.8):
            continue
        if not (reference * 0.62 <= width <= reference * 3.8):
            continue
        aspect = height / float(max(1, width))
        if not 0.42 <= aspect <= 2.9:
            continue
        separation = sign * (float(x0) - float(body.center))
        if not (reference * 0.12 <= separation <= reference * 5.2):
            continue
        result.append(DisplayHead(
            column=column.index,
            x0=int(x0), y0=int(y0), x1=int(x1), y1=int(y1),
        ))
    # Large connected objects can overlap after dilation; keep the smallest box
    # around each vertical neighborhood rather than publishing duplicates.
    result.sort(key=lambda head: (head.y0, head.x0, head.height * head.width))
    deduped: list[DisplayHead] = []
    for head in result:
        if any(abs(head.y0 - kept.y0) <= reference * 0.35 for kept in deduped):
            continue
        deduped.append(head)
    return deduped


def infer_dictionary_page_layout(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int = 0,
) -> DictionaryPageLayout:
    source, canonical, transform, effective = _canonical_analysis_page(
        image, settings, page_index,
    )
    top, bottom, starts, rights, gutters = _projection_geometry(canonical, effective)
    gray = np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8)
    page_ink = analysis_ink_mask(gray, effective)
    seed = max(8.0, float(getattr(effective, "character_height", 26) or 26))

    raw_runs: list[list[tuple[int, int]]] = []
    strips: list[np.ndarray] = []
    for left, right in zip(starts, rights):
        left = max(0, min(canonical.width - 1, int(left)))
        right = max(left + 1, min(canonical.width, int(right)))
        width = right - left
        strip_width = _leading_strip_width(width, seed)
        strip = page_ink[top:bottom, left:left + strip_width]
        strips.append(strip)
        raw_runs.append(_line_runs(strip, seed))

    reference = _robust_normal_height(raw_runs, seed)
    indent_type = _indent_type(settings)
    columns: list[ColumnDesign] = []
    for index, (left, right, gutter, strip, runs) in enumerate(
        zip(starts, rights, gutters, strips, raw_runs)
    ):
        column = ColumnDesign(index=index, left=int(left), right=int(right), gutter_after=int(gutter))
        previous_end = 0
        for y0, y1 in runs:
            line = _line_feature(index, strip, y0, y1, reference, previous_end)
            previous_end = max(previous_end, int(y1))
            if line is not None and reference * 0.45 <= line.height <= reference * 1.55:
                column.lines.append(line)
        column.indent_modes = _cluster_indent_modes(column.lines, reference)
        _choose_semantic_modes(column, indent_type, reference)
        columns.append(column)

    # Page-level design transfer: if one column proves a recurring entry offset,
    # a single matching block in another column is still part of the same page
    # design. This is how sparse columns avoid requiring duplicate local entries.
    normalized_entry_offsets: list[float] = []
    for column in columns:
        if column.body_mode is None:
            continue
        sign = 1.0 if indent_type == "headword" else -1.0
        for mode in column.entry_modes:
            normalized_entry_offsets.append(
                sign * (mode.center - column.body_mode.center) / max(1.0, reference)
            )
    page_entry_offset = (
        float(np.median(np.asarray(normalized_entry_offsets, dtype=float)))
        if normalized_entry_offsets else None
    )
    if page_entry_offset is not None:
        sign = 1.0 if indent_type == "headword" else -1.0
        for column in columns:
            body = column.body_mode
            if body is None:
                continue
            predicted = body.center + sign * page_entry_offset * reference
            existing_lines = {id(line) for mode in column.entry_modes for line in mode.lines}
            sparse = [
                line for line in column.lines
                if id(line) not in existing_lines
                and line.anchor_x is not None
                and abs(float(line.anchor_x) - predicted) <= reference * 0.32
            ]
            if sparse:
                mode = IndentMode(
                    center=float(np.median([float(line.anchor_x or 0) for line in sparse])),
                    tolerance=reference * 0.32,
                    lines=sparse,
                    shape_consensus=_shape_consensus(sparse),
                    role="entry",
                )
                column.entry_modes.append(mode)

    pitch = _ordinary_pitch(columns, reference)
    char_width = _ordinary_char_width(columns, reference)
    display_heads: list[DisplayHead] = []
    for column in columns:
        left = max(0, min(canonical.width - 1, column.left))
        right = max(left + 1, min(canonical.width, column.right))
        strip_width = _leading_strip_width(right - left, reference)
        strip = page_ink[top:bottom, left:left + strip_width]
        display_heads.extend(_display_heads(column, strip, reference, indent_type))

    display_width = float(np.median([head.width for head in display_heads])) if display_heads else 0.0
    display_height = float(np.median([head.height for head in display_heads])) if display_heads else 0.0

    body_lines = sum(column.body_mode.support for column in columns if column.body_mode is not None)
    entry_lines = sum(mode.support for column in columns for mode in column.entry_modes)
    body_columns = sum(column.body_mode is not None for column in columns)
    # A dense body-only continuation page is a valid, informative layout and
    # should confidently produce zero entries rather than falling back to a
    # candidate generator that fires on every ordinary line.
    enough_body = body_lines >= max(7, 3 * max(1, len(columns)))
    reliable = bool(columns and body_columns >= max(1, len(columns) - 1) and (entry_lines >= 2 or display_heads or enough_body))
    reason = (
        f"{len(columns)} columns; body={body_lines}; entry={entry_lines}; "
        f"display={len(display_heads)}; h={reference:.1f}; pitch={pitch:.1f}"
    )
    return DictionaryPageLayout(
        transform=transform,
        source_size=source.size,
        canonical_size=canonical.size,
        body_top=int(top), body_bottom=int(bottom), columns=columns,
        ordinary_line_height=float(reference),
        ordinary_line_pitch=float(pitch),
        ordinary_char_width=float(char_width),
        ordinary_char_height=float(reference),
        indent_type=indent_type,
        display_heads=display_heads,
        display_head_width=display_width,
        display_head_height=display_height,
        reliable=reliable,
        reason=reason,
    )


def _boundary_before(
    lines: list[LayoutLine],
    y0: int,
    reference: float,
) -> int:
    previous = max((line.y1 for line in lines if line.y1 <= y0), default=None)
    if previous is None:
        return max(0, int(round(y0 - reference * 0.35)))
    gap = max(1, int(y0) - int(previous))
    # Mid-whitespace is stable across ascenders/descenders and never cuts the
    # preceding definition or the new headword glyph.
    return int(previous) + max(1, gap // 2)


def _source_boundary_entry(
    layout: DictionaryPageLayout,
    column: ColumnDesign,
    canonical_y: int,
    *,
    kind: str,
    confidence: float,
) -> Entry:
    canonical_x = int(column.left)
    source_x, source_y = layout.transform.canonical_to_source_point(
        canonical_x,
        int(layout.body_top) + int(canonical_y),
        layout.source_size,
    )
    return Entry(
        word="",
        x=int(source_x),
        y=int(source_y),
        confidence=float(confidence),
        ocr_source="ordinary_page_design",
        issue_type=kind,
    )


def infer_entry_boundaries(
    layout: DictionaryPageLayout,
    *,
    page_sections: list[Any] | None = None,
) -> list[Entry]:
    entries: list[Entry] = []
    reference = max(1.0, float(layout.ordinary_line_height))

    for column in layout.columns:
        entry_ids = {id(line) for mode in column.entry_modes for line in mode.lines}
        for line in column.lines:
            if id(line) not in entry_ids:
                line.role = "body" if column.body_mode and line in column.body_mode.lines else "unknown"
                continue
            line.role = "entry"
            local_y = _boundary_before(column.lines, line.y0, reference)
            entry = _source_boundary_entry(
                layout, column, local_y,
                kind="ORDINARY_PAGE_DESIGN_ENTRY",
                confidence=0.97 if line.has_small_prefix else 0.96,
            )
            if page_sections and not any(int(section.top_v) <= entry.y < int(section.bottom_v) for section in page_sections):
                continue
            entries.append(entry)

    for head in layout.display_heads:
        column = layout.columns[head.column]
        local_y = _boundary_before(column.lines, head.y0, reference)
        entry = _source_boundary_entry(
            layout, column, local_y,
            kind="ORDINARY_PAGE_DESIGN_DISPLAY_HEAD",
            confidence=0.98,
        )
        if page_sections and not any(int(section.top_v) <= entry.y < int(section.bottom_v) for section in page_sections):
            continue
        # Do not duplicate a normal entry boundary in the same vertical block.
        if any(abs(existing.y - entry.y) <= reference * 0.42 for existing in entries):
            continue
        entry.ocr_single_cjk = True
        entry.ocr_oversized_cjk = True
        entry.ocr_visual_run_height = float(head.height)
        entry.ocr_line_height_reference = float(reference)
        entries.append(entry)

    return entries


def detect_entries_from_page_design(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int = 0,
    page_sections: list[Any] | None = None,
) -> LayoutDetectionResult:
    layout = infer_dictionary_page_layout(image, settings, page_index=page_index)
    entries = infer_entry_boundaries(layout, page_sections=page_sections) if layout.reliable else []
    return LayoutDetectionResult(entries=entries, layout=layout)
