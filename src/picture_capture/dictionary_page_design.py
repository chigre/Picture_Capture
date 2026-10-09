from __future__ import annotations

"""OCR-free dictionary page-design inference and entry-boundary drawing.

The unit of reasoning is the *designed page*.  We first recover the page grammar
that a typesetter would have specified: reading transform, physical page
regions, body and columns, true gutters, ordinary line/character scale,
indentation modes, and optional display-size headwords.  Entry boundaries are
then consequences of that recovered design.

No text recognition is used.  Small numeric/superscript prefixes are modifiers
before the first full-height structural glyph.  Persistent vertical rules are
gutter decoration rather than column starts.  Oversized heads form a second
typography size level; they are not a rescue heuristic layered on normal lines.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from .image_utils import normalize_page_rgb
from .layout_detection import _projection_layout_estimate, analysis_ink_mask
from .layout_transform import LayoutTransform
from .models import AppSettings, Entry
from .ordinary_visual import _components, _fill_short_gaps, _runs
from .profile_indent_ui import indent_type_label
from .profile_semantics import (
    effective_page_settings,
    excluded_source_side,
    excluded_source_side_percent,
    page_template_analysis_image,
)


Box = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class PageRegion:
    name: str
    source_box: Box
    canonical_box: Box
    origin: str  # configured / inferred


@dataclass(slots=True)
class PageRegions:
    body: PageRegion
    header: PageRegion | None = None
    footer: PageRegion | None = None
    side: PageRegion | None = None


@dataclass(slots=True)
class LayoutLine:
    column: int
    y0: int
    y1: int
    first_x: int
    anchor_x: int | None
    anchor_width: int
    anchor_height: int
    gap_before: int
    patch: np.ndarray
    has_small_prefix: bool = False
    role: str = "unknown"

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
    regions: PageRegions
    body_top: int
    body_bottom: int
    columns: list[ColumnDesign]
    ordinary_line_height: float
    ordinary_line_pitch: float
    ordinary_char_width: float
    ordinary_char_height: float
    indent_type: str
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


def _analysis_page(
    image: Image.Image,
    settings: AppSettings,
    page_index: int,
) -> tuple[Image.Image, Image.Image, LayoutTransform, AppSettings]:
    source = normalize_page_rgb(image)
    effective = effective_page_settings(settings, source.size, page_index)
    template = page_template_analysis_image(source, settings, page_index)
    transform = LayoutTransform(
        str(getattr(settings, "layout_transform", "identity") or "identity")
    )
    return source, transform.canonical_image_for_analysis(template), transform, effective


def _initial_geometry(
    canonical: Image.Image,
    effective: AppSettings,
) -> tuple[int, int, list[int], list[int]]:
    estimate = _projection_layout_estimate(canonical, effective)
    top = max(0, min(canonical.height - 1, int(estimate.start_y)))
    bottom = max(top + 1, min(canonical.height, int(estimate.bottom_y)))
    starts = [int(x) for x in estimate.column_starts]
    rights = [int(x) for x in estimate.column_rights]
    if not starts:
        starts = [
            int(estimate.manual_x)
            + i * (int(estimate.column_width) + int(estimate.gutter))
            for i in range(max(1, int(estimate.columns)))
        ]
    if len(rights) != len(starts):
        rights = [
            min(canonical.width, x + int(estimate.column_width)) for x in starts
        ]
    return top, bottom, starts, rights


def _persistent_rule_mask(body_ink: np.ndarray, reference: float) -> np.ndarray:
    """Return X columns occupied by persistent printed vertical rules."""
    if body_ink.ndim != 2 or body_ink.size == 0:
        return np.zeros(0, dtype=bool)
    count = min(
        20,
        max(5, body_ink.shape[0] // max(24, round(reference * 2.5))),
    )
    blocks = [block for block in np.array_split(body_ink, count, axis=0) if block.size]
    density = body_ink.mean(axis=0)
    persistence = np.vstack([
        block.mean(axis=0) >= 0.18 for block in blocks
    ]).mean(axis=0)
    rule = (density >= 0.34) & (persistence >= 0.72)
    pad = max(1, round(reference * 0.08))
    expanded = rule.copy()
    for shift in range(1, pad + 1):
        expanded[shift:] |= rule[:-shift]
        expanded[:-shift] |= rule[shift:]
    return expanded


def _robust_first_text_x(region: np.ndarray, reference: float) -> int | None:
    if region.ndim != 2 or region.size == 0:
        return None
    values: list[int] = []
    minimum_row_ink = max(2, round(reference * 0.16))
    for row in region:
        xs = np.flatnonzero(row)
        if xs.size >= minimum_row_ink:
            values.append(int(xs[0]))
    if len(values) < 6:
        return None
    return int(round(float(np.quantile(np.asarray(values, dtype=float), 0.12))))


def _refine_column_geometry(
    page_ink: np.ndarray,
    top: int,
    bottom: int,
    starts: list[int],
    rights: list[int],
    reference: float,
) -> tuple[list[int], list[int], list[int]]:
    """Recover text-column edges after suppressing divider rules geometrically."""
    if not starts:
        return [], [], []
    body = page_ink[max(0, top):max(top + 1, bottom), :].copy()
    rules = _persistent_rule_mask(body, reference)
    if rules.size:
        body[:, rules] = False

    refined = list(starts)
    for index in range(len(starts)):
        if index == 0:
            search_left = max(0, starts[index] - round(reference * 1.5))
        else:
            search_left = max(
                0,
                rights[index - 1] + max(1, round(reference * 0.20)),
            )
        search_right = min(
            body.shape[1],
            max(search_left + 2, rights[index] + round(reference * 1.5)),
        )
        candidate = _robust_first_text_x(
            body[:, search_left:search_right], reference,
        )
        if candidate is not None:
            refined[index] = search_left + candidate

    fixed_rights: list[int] = []
    for index, start in enumerate(refined):
        right = rights[index] if index < len(rights) else start + 1
        if index + 1 < len(refined):
            right = min(right, refined[index + 1] - 1)
        fixed_rights.append(max(start + 1, int(right)))
    gutters = [
        max(0, refined[i + 1] - fixed_rights[i])
        if i + 1 < len(refined) else 0
        for i in range(len(refined))
    ]
    return refined, fixed_rights, gutters


def _leading_width(column_width: int, scale: float) -> int:
    return max(
        24,
        min(column_width, max(round(column_width * 0.42), round(scale * 7.0), 96)),
    )


def _line_runs(ink: np.ndarray, scale: float) -> list[tuple[int, int]]:
    if ink.ndim != 2 or ink.size == 0:
        return []
    active = ink.sum(axis=1) >= max(2, round(ink.shape[1] * 0.003))
    active = _fill_short_gaps(active, max(1, round(scale * 0.09)))
    return [
        (int(y0), int(y1))
        for y0, y1 in _runs(active)
        if scale * 0.26 <= y1 - y0 <= scale * 1.90
    ]


def _normal_height(
    runs_by_column: list[list[tuple[int, int]]],
    fallback: float,
) -> float:
    values = np.asarray([
        float(y1 - y0) for runs in runs_by_column for y0, y1 in runs
    ])
    seed = max(6.0, float(fallback))
    if values.size == 0:
        return seed
    plausible = values[(values >= seed * 0.45) & (values <= seed * 1.55)]
    sample = plausible if plausible.size >= 5 else values
    center = float(np.median(sample))
    deviation = np.abs(sample - center)
    mad = float(np.median(deviation)) if deviation.size else 0.0
    if mad > 0:
        kept = sample[deviation <= max(2.0, 3.5 * mad)]
        if kept.size:
            center = float(np.median(kept))
    return max(seed * 0.55, min(seed * 1.35, center))


def _horizontal_components(line: np.ndarray, reference: float) -> list[tuple[int, int, int]]:
    if line.ndim != 2 or line.size == 0:
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
    line = ink[y0:y1]
    sturdy = line.sum(axis=0) >= max(1, round(max(1, y1 - y0) * 0.055))
    starts = np.flatnonzero(sturdy)
    if starts.size == 0:
        return None
    first_x = int(starts[0])
    threshold = max(4, round(reference * 0.56))
    anchors = [
        part for part in _horizontal_components(line, reference)
        if part[2] >= threshold and part[1] - part[0] >= 2
    ]
    anchor = anchors[0] if anchors else None
    anchor_x = int(anchor[0]) if anchor else None
    anchor_width = int(anchor[1] - anchor[0]) if anchor else 0
    anchor_height = int(anchor[2]) if anchor else 0
    has_small_prefix = bool(
        anchor_x is not None and first_x < anchor_x - reference * 0.12
    )
    if anchor_x is None:
        patch = np.zeros((0, 0), dtype=bool)
    else:
        py0 = max(0, y0 - round(reference * 0.10))
        py1 = min(ink.shape[0], y1 + round(reference * 0.10))
        px0 = max(0, anchor_x - round(reference * 0.05))
        px1 = min(ink.shape[1], anchor_x + round(reference * 0.78))
        patch = ink[py0:py1, px0:px1].copy()
    return LayoutLine(
        column=column,
        y0=y0,
        y1=y1,
        first_x=first_x,
        anchor_x=anchor_x,
        anchor_width=anchor_width,
        anchor_height=anchor_height,
        gap_before=max(0, y0 - previous_end),
        patch=patch,
        has_small_prefix=has_small_prefix,
    )


def _shape_signature(patch: np.ndarray) -> tuple[np.ndarray, float]:
    """Return the historical normalized 12x24 patch vector and its norm."""
    image = Image.fromarray((patch.astype(np.uint8) * 255), mode="L")
    try:
        values = np.asarray(
            image.resize((12, 24), Image.Resampling.NEAREST),
            dtype=np.float32,
        ).ravel().copy()
    finally:
        image.close()
    values -= float(values.mean())
    return values, float(np.linalg.norm(values))


def _shape_consensus(lines: list[LayoutLine]) -> float:
    usable = [line for line in lines if line.patch.size]
    if len(usable) < 2:
        return 0.0

    # The historical implementation called _patch_similarity for every pair,
    # repeatedly resizing, centering and normalizing the same patches O(N^2)
    # times. Preserve the same pairwise cosine comparison and threshold while
    # preparing each patch only once per cluster.
    prepared = [_shape_signature(line.patch) for line in usable]
    count = float(len(prepared))
    best = 0.0
    for prototype_values, prototype_norm in prepared:
        matched = 0
        if prototype_norm > 1e-6:
            for line_values, line_norm in prepared:
                if line_norm <= 1e-6:
                    continue
                similarity = float(
                    np.dot(prototype_values, line_values)
                    / (prototype_norm * line_norm)
                )
                matched += int(similarity >= 0.52)
        best = max(best, matched / count)
    return best


def _indent_modes(lines: list[LayoutLine], reference: float) -> list[IndentMode]:
    usable = [line for line in lines if line.anchor_x is not None]
    clusters: list[list[LayoutLine]] = []
    tolerance = max(3.0, reference * 0.24)
    for line in sorted(usable, key=lambda item: int(item.anchor_x or 0)):
        target = None
        for cluster in clusters:
            center = float(np.median([float(item.anchor_x or 0) for item in cluster]))
            if abs(float(line.anchor_x or 0) - center) <= tolerance:
                target = cluster
                break
        if target is None:
            clusters.append([line])
        else:
            target.append(line)

    result: list[IndentMode] = []
    for cluster in clusters:
        center = float(np.median([float(line.anchor_x or 0) for line in cluster]))
        deviation = np.asarray([
            abs(float(line.anchor_x or 0) - center) for line in cluster
        ])
        q90 = float(np.quantile(deviation, 0.90)) if deviation.size else 0.0
        result.append(IndentMode(
            center=center,
            tolerance=max(
                reference * 0.14,
                min(reference * 0.34, q90 + reference * 0.08),
            ),
            lines=list(cluster),
            shape_consensus=_shape_consensus(cluster),
        ))
    return sorted(result, key=lambda mode: mode.center)


def _assign_indent_semantics(
    column: ColumnDesign,
    indent_type: str,
    reference: float,
) -> None:
    if not column.indent_modes:
        return
    count = max(1, sum(mode.support for mode in column.indent_modes))
    stable = [
        mode for mode in column.indent_modes
        if mode.support >= max(3, round(count * 0.12))
    ]
    if not stable:
        stable = [max(column.indent_modes, key=lambda mode: mode.support)]
    body = (
        min(stable, key=lambda mode: mode.center)
        if indent_type == "headword"
        else max(stable, key=lambda mode: mode.center)
    )
    body.role = "body"
    column.body_mode = body
    sign = 1.0 if indent_type == "headword" else -1.0
    entries: list[IndentMode] = []
    for mode in column.indent_modes:
        if mode is body:
            continue
        offset = sign * (mode.center - body.center)
        if reference * 0.42 <= offset <= reference * 5.0 and mode.support >= 2:
            mode.role = "entry"
            entries.append(mode)
    column.entry_modes = entries


def _line_pitch(columns: list[ColumnDesign], reference: float) -> float:
    gaps: list[float] = []
    for column in columns:
        ys = sorted(line.y0 for line in column.lines)
        gaps.extend(
            float(b - a) for a, b in zip(ys, ys[1:])
            if reference * 0.75 <= b - a <= reference * 2.4
        )
    return float(np.median(gaps)) if gaps else float(reference * 1.25)


def _char_width(columns: list[ColumnDesign], reference: float) -> float:
    widths = [
        float(line.anchor_width)
        for column in columns
        for line in column.lines
        if reference * 0.22 <= line.anchor_width <= reference * 1.45
        and reference * 0.55 <= line.anchor_height <= reference * 1.35
    ]
    return float(np.median(widths)) if len(widths) >= 5 else float(reference)


def _merge_boxes(
    boxes: list[tuple[int, int, int, int, int]],
    reference: float,
) -> list[tuple[int, int, int, int, int]]:
    """Merge only typography-sized fragments that can belong to one large glyph."""
    groups: list[list[int]] = []
    for x0, y0, x1, y1, area in boxes:
        width, height = x1 - x0, y1 - y0
        if area < reference * reference * 0.02:
            continue
        # Upper bounds are only anti-illustration guards.  Display typography can
        # legitimately be four or five times an ordinary row.
        if width > reference * 5.8 or height > reference * 5.8:
            continue
        if not (
            height >= reference * 1.05
            or (width >= reference * 1.00 and height >= reference * 0.58)
        ):
            continue
        groups.append([int(x0), int(y0), int(x1), int(y1), int(area)])

    changed = True
    while changed:
        changed = False
        output: list[list[int]] = []
        while groups:
            current = groups.pop(0)
            rest: list[list[int]] = []
            for other in groups:
                hgap = max(0, max(current[0], other[0]) - min(current[2], other[2]))
                vgap = max(0, max(current[1], other[1]) - min(current[3], other[3]))
                xov = max(0, min(current[2], other[2]) - max(current[0], other[0]))
                yov = max(0, min(current[3], other[3]) - max(current[1], other[1]))
                join = (
                    (xov >= reference * 0.18 and vgap <= reference * 0.36)
                    or (yov >= reference * 0.26 and hgap <= reference * 0.58)
                )
                if join:
                    current = [
                        min(current[0], other[0]),
                        min(current[1], other[1]),
                        max(current[2], other[2]),
                        max(current[3], other[3]),
                        current[4] + other[4],
                    ]
                    changed = True
                else:
                    rest.append(other)
            groups = rest
            output.append(current)
        groups = output
    return [tuple(group) for group in groups]


def _display_heads(
    column: ColumnDesign,
    ink: np.ndarray,
    reference: float,
    indent_type: str,
) -> list[DisplayHead]:
    if column.body_mode is None or ink.size == 0:
        return []
    sign = 1.0 if indent_type == "headword" else -1.0
    candidates = _merge_boxes(_components(ink), reference)

    # Independent vertical-block view catches a fragmented large glyph whose
    # individual radicals never exceed the ordinary size threshold.
    active = ink.sum(axis=1) >= max(2, round(ink.shape[1] * 0.004))
    active = _fill_short_gaps(active, max(1, round(reference * 0.22)))
    for y0, y1 in _runs(active):
        height = y1 - y0
        if not (reference * 1.35 <= height <= reference * 5.8):
            continue
        roi = ink[y0:y1]
        xs = np.flatnonzero(roi.any(axis=0))
        if xs.size:
            candidates.append((
                int(xs[0]), int(y0), int(xs[-1] + 1), int(y1), int(roi.sum())
            ))

    result: list[DisplayHead] = []
    for x0, y0, x1, y1, area in candidates:
        width, height = x1 - x0, y1 - y0
        if area < reference * reference * 0.09:
            continue
        if not (reference * 1.35 <= height <= reference * 5.8):
            continue
        if not (reference * 0.55 <= width <= reference * 5.0):
            continue
        if not 0.34 <= height / float(max(1, width)) <= 3.6:
            continue
        offset = sign * (float(x0) - column.body_mode.center)
        if not (reference * 0.10 <= offset <= reference * 5.4):
            continue
        result.append(DisplayHead(column.index, x0, y0, x1, y1))

    result.sort(key=lambda head: (head.y0, head.x0, head.width * head.height))
    deduped: list[DisplayHead] = []
    for head in result:
        if any(
            abs(head.y0 - kept.y0) <= reference * 0.42
            and abs(head.x0 - kept.x0) <= reference * 0.65
            for kept in deduped
        ):
            continue
        deduped.append(head)
    return deduped


def _regions(
    settings: AppSettings,
    page_index: int,
    source_size: tuple[int, int],
    transform: LayoutTransform,
    body_canonical: Box,
) -> PageRegions:
    width, height = source_size
    header = footer = side_region = None
    if str(getattr(settings, "profile_header_mode", "auto") or "auto") == "present":
        amount = round(height * max(0.0, min(35.0, float(settings.profile_header_percent))) / 100.0)
        box = (0, 0, width, amount)
        header = PageRegion("header", box, transform.source_box_to_canonical(box, source_size), "configured")
    elif body_canonical[1] > 0:
        cbox = (0, 0, transform.canonical_size(source_size)[0], body_canonical[1])
        header = PageRegion("header", transform.canonical_box_to_source(cbox, source_size), cbox, "inferred")

    if str(getattr(settings, "profile_footer_mode", "auto") or "auto") == "present":
        amount = round(height * max(0.0, min(35.0, float(settings.profile_footer_percent))) / 100.0)
        box = (0, max(0, height - amount), width, height)
        footer = PageRegion("footer", box, transform.source_box_to_canonical(box, source_size), "configured")

    side_name = excluded_source_side(settings, page_index)
    if side_name is not None:
        amount = round(width * excluded_source_side_percent(settings, page_index) / 100.0)
        box = (
            (0, 0, amount, height)
            if side_name == "left"
            else (max(0, width - amount), 0, width, height)
        )
        side_region = PageRegion("side", box, transform.source_box_to_canonical(box, source_size), "configured")

    body = PageRegion(
        "body",
        transform.canonical_box_to_source(body_canonical, source_size),
        body_canonical,
        "inferred",
    )
    return PageRegions(body=body, header=header, footer=footer, side=side_region)


def infer_dictionary_page_layout(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int = 0,
) -> DictionaryPageLayout:
    source, canonical, transform, effective = _analysis_page(image, settings, page_index)
    top, bottom, starts, rights = _initial_geometry(canonical, effective)
    page_ink = analysis_ink_mask(
        np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8), effective
    )
    seed = max(8.0, float(getattr(effective, "character_height", 26) or 26))
    starts, rights, gutters = _refine_column_geometry(
        page_ink, top, bottom, starts, rights, seed
    )

    def column_strips(scale: float) -> tuple[list[np.ndarray], list[list[tuple[int, int]]]]:
        strips: list[np.ndarray] = []
        runs: list[list[tuple[int, int]]] = []
        for left, right in zip(starts, rights):
            width = max(1, right - left)
            strip = page_ink[top:bottom, left:left + _leading_width(width, scale)]
            strips.append(strip)
            runs.append(_line_runs(strip, scale))
        return strips, runs

    strips, raw_runs = column_strips(seed)
    reference = _normal_height(raw_runs, seed)
    starts, rights, gutters = _refine_column_geometry(
        page_ink, top, bottom, starts, rights, reference
    )
    strips, raw_runs = column_strips(reference)

    indent_type = _indent_type(settings)
    columns: list[ColumnDesign] = []
    for index, (left, right, gutter, strip, runs) in enumerate(
        zip(starts, rights, gutters, strips, raw_runs)
    ):
        column = ColumnDesign(index, left, right, gutter)
        previous_end = 0
        for y0, y1 in runs:
            line = _line_feature(index, strip, y0, y1, reference, previous_end)
            previous_end = max(previous_end, y1)
            if line is not None and reference * 0.45 <= line.height <= reference * 1.55:
                column.lines.append(line)
        column.indent_modes = _indent_modes(column.lines, reference)
        _assign_indent_semantics(column, indent_type, reference)
        columns.append(column)

    # Transfer the page's proven entry offset into sparse columns.
    sign = 1.0 if indent_type == "headword" else -1.0
    offsets = [
        sign * (mode.center - column.body_mode.center) / max(1.0, reference)
        for column in columns if column.body_mode is not None
        for mode in column.entry_modes
    ]
    if offsets:
        typical = float(np.median(offsets))
        for column in columns:
            if column.body_mode is None:
                continue
            predicted = column.body_mode.center + sign * typical * reference
            assigned = {id(line) for mode in column.entry_modes for line in mode.lines}
            sparse = [
                line for line in column.lines
                if id(line) not in assigned
                and line.anchor_x is not None
                and abs(float(line.anchor_x) - predicted) <= reference * 0.32
            ]
            if sparse:
                column.entry_modes.append(IndentMode(
                    center=float(np.median([float(line.anchor_x or 0) for line in sparse])),
                    tolerance=reference * 0.32,
                    lines=sparse,
                    shape_consensus=_shape_consensus(sparse),
                    role="entry",
                ))

    char_width = _char_width(columns, reference)
    pitch = _line_pitch(columns, reference)
    display_heads = [
        head
        for column, strip in zip(columns, strips)
        for head in _display_heads(column, strip, reference, indent_type)
    ]
    display_width = float(np.median([head.width for head in display_heads])) if display_heads else 0.0
    display_height = float(np.median([head.height for head in display_heads])) if display_heads else 0.0

    body_lines = sum(
        column.body_mode.support for column in columns if column.body_mode is not None
    )
    entry_lines = sum(mode.support for column in columns for mode in column.entry_modes)
    body_columns = sum(column.body_mode is not None for column in columns)
    enough_body = body_lines >= max(7, 3 * max(1, len(columns)))
    reliable = bool(
        columns
        and body_columns >= max(1, len(columns) - 1)
        and (entry_lines >= 2 or display_heads or enough_body)
    )

    body_left = min((column.left for column in columns), default=0)
    body_right = max((column.right for column in columns), default=canonical.width)
    regions = _regions(
        settings,
        page_index,
        source.size,
        transform,
        (body_left, top, body_right, bottom),
    )
    reason = (
        f"{len(columns)} columns; body={body_lines}; entry={entry_lines}; "
        f"display={len(display_heads)}; line_h={reference:.1f}; "
        f"char_w={char_width:.1f}; pitch={pitch:.1f}"
    )
    return DictionaryPageLayout(
        transform=transform,
        source_size=source.size,
        canonical_size=canonical.size,
        regions=regions,
        body_top=top,
        body_bottom=bottom,
        columns=columns,
        ordinary_line_height=reference,
        ordinary_line_pitch=pitch,
        ordinary_char_width=char_width,
        ordinary_char_height=reference,
        indent_type=indent_type,
        display_heads=display_heads,
        display_head_width=display_width,
        display_head_height=display_height,
        reliable=reliable,
        reason=reason,
    )


def layout_diagnostics(layout: DictionaryPageLayout) -> dict[str, Any]:
    """Serialize the recovered 'page specification' for debugging/UI inspection."""
    def region_value(region: PageRegion | None) -> dict[str, Any] | None:
        if region is None:
            return None
        return {
            "source_box": list(region.source_box),
            "canonical_box": list(region.canonical_box),
            "origin": region.origin,
        }

    return {
        "reliable": bool(layout.reliable),
        "reason": layout.reason,
        "reading_transform": layout.transform.kind,
        "indent_type": layout.indent_type,
        "regions": {
            "header": region_value(layout.regions.header),
            "footer": region_value(layout.regions.footer),
            "side": region_value(layout.regions.side),
            "body": region_value(layout.regions.body),
        },
        "ordinary": {
            "line_height": layout.ordinary_line_height,
            "line_pitch": layout.ordinary_line_pitch,
            "char_width": layout.ordinary_char_width,
            "char_height": layout.ordinary_char_height,
        },
        "display_head": {
            "present": layout.has_display_heads,
            "count": len(layout.display_heads),
            "width": layout.display_head_width,
            "height": layout.display_head_height,
        },
        "columns": [
            {
                "index": column.index,
                "start_x": column.left,
                "end_x": column.right,
                "width": column.width,
                "gutter_after": column.gutter_after,
                "body_indent": (
                    column.body_mode.center if column.body_mode is not None else None
                ),
                "indent_modes": [
                    {
                        "center": mode.center,
                        "tolerance": mode.tolerance,
                        "support": mode.support,
                        "role": mode.role,
                        "shape_consensus": mode.shape_consensus,
                    }
                    for mode in column.indent_modes
                ],
            }
            for column in layout.columns
        ],
    }


def _boundary_before(lines: list[LayoutLine], y0: int, reference: float) -> int:
    previous = max((line.y1 for line in lines if line.y1 <= y0), default=None)
    if previous is None:
        return max(0, int(round(y0 - reference * 0.35)))
    gap = max(1, y0 - previous)
    return previous + max(1, gap // 2)


def _entry(
    layout: DictionaryPageLayout,
    column: ColumnDesign,
    local_y: int,
    kind: str,
    confidence: float,
) -> Entry:
    x, y = layout.transform.canonical_to_source_point(
        column.left,
        layout.body_top + local_y,
        layout.source_size,
    )
    return Entry(
        word="",
        x=int(x),
        y=int(y),
        confidence=confidence,
        ocr_source="ordinary_page_design",
        issue_type=kind,
    )


def infer_entry_boundaries(
    layout: DictionaryPageLayout,
    *,
    page_sections: list[Any] | None = None,
) -> list[Entry]:
    entries: list[Entry] = []
    reference = max(1.0, layout.ordinary_line_height)
    for column in layout.columns:
        entry_ids = {id(line) for mode in column.entry_modes for line in mode.lines}
        for line in column.lines:
            if id(line) not in entry_ids:
                line.role = "body" if column.body_mode and line in column.body_mode.lines else "unknown"
                continue
            line.role = "entry"
            boundary = _boundary_before(column.lines, line.y0, reference)
            item = _entry(
                layout,
                column,
                boundary,
                "ORDINARY_PAGE_DESIGN_ENTRY",
                0.97 if line.has_small_prefix else 0.96,
            )
            if page_sections and not any(
                int(section.top_v) <= item.y < int(section.bottom_v)
                for section in page_sections
            ):
                continue
            entries.append(item)

    for head in layout.display_heads:
        column = layout.columns[head.column]
        boundary = _boundary_before(column.lines, head.y0, reference)
        item = _entry(
            layout,
            column,
            boundary,
            "ORDINARY_PAGE_DESIGN_DISPLAY_HEAD",
            0.98,
        )
        if page_sections and not any(
            int(section.top_v) <= item.y < int(section.bottom_v)
            for section in page_sections
        ):
            continue
        if any(abs(existing.y - item.y) <= reference * 0.42 for existing in entries):
            continue
        item.ocr_single_cjk = True
        item.ocr_oversized_cjk = True
        item.ocr_visual_run_height = float(head.height)
        item.ocr_line_height_reference = reference
        entries.append(item)
    return entries


def _detect_entries_from_page_design_base(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int = 0,
    page_sections: list[Any] | None = None,
) -> LayoutDetectionResult:
    """Retain the original unrefined materialization for focused diagnostics."""
    layout = infer_dictionary_page_layout(image, settings, page_index=page_index)
    entries = infer_entry_boundaries(layout, page_sections=page_sections) if layout.reliable else []
    return LayoutDetectionResult(entries=entries, layout=layout)


def detect_entries_from_page_design(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int = 0,
    page_sections: list[Any] | None = None,
) -> LayoutDetectionResult:
    """Use the refined detector without requiring process-global rebinding."""
    # Local import avoids the base <-> refined module cycle. The refined
    # implementation consumes base geometry helpers but never calls this public
    # forwarding function, so call-time delegation cannot recurse.
    from .dictionary_page_design_refined import (
        detect_entries_from_page_design as refined_detect_entries,
    )

    return refined_detect_entries(
        image,
        settings,
        page_index=page_index,
        page_sections=page_sections,
    )
