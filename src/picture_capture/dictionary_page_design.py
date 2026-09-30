from __future__ import annotations

"""OCR-free dictionary page-design inference and entry-boundary drawing.

The unit of reasoning here is the *designed page*, not an isolated candidate
line.  We first recover the page grammar that a typesetter would have specified:
reading transform, physical page regions, body and columns, gutters, ordinary
line/character scale, indentation modes, and optional display-size headwords.
Entry boundaries are then consequences of that recovered design.

No text recognition is used.  Small numeric/superscript prefixes are treated as
modifiers before the first full-height structural glyph.  Persistent vertical
rules are treated as gutter decoration rather than column starts.  Oversized
heads are a second typography size level, not a rescue heuristic layered on top
of normal-line detection.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from .image_utils import normalize_page_rgb
from .layout_detection import _projection_layout_estimate, analysis_ink_mask
from .layout_transform import LayoutTransform
from .models import AppSettings, Entry
from .ordinary_visual import _components, _fill_short_gaps, _patch_similarity, _runs
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
    regions: PageRegions
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
    transform = LayoutTransform(
        str(getattr(settings, "layout_transform", "identity") or "identity")
    )
    canonical = transform.canonical_image_for_analysis(template)
    return source, canonical, transform, effective


def _projection_geometry(
    canonical: Image.Image,
    effective: AppSettings,
) -> tuple[int, int, list[int], list[int], list[int]]:
    """Initial body/column geometry, before text-edge refinement."""
    estimate = _projection_layout_estimate(canonical, effective)
    top = max(0, min(canonical.height - 1, int(estimate.start_y)))
    bottom = max(top + 1, min(canonical.height, int(estimate.bottom_y)))
    starts = list(estimate.column_starts)
    rights = list(estimate.column_rights)
    if not starts:
        starts = [
            int(estimate.manual_x)
            + i * (int(estimate.column_width) + int(estimate.gutter))
            for i in range(max(1, int(estimate.columns)))
        ]
    if len(rights) != len(starts):
        rights = [
            min(canonical.width, int(x) + int(estimate.column_width)) for x in starts
        ]
    gutters = [
        max(0, int(starts[i + 1]) - int(rights[i]))
        if i + 1 < len(starts) else 0
        for i in range(len(starts))
    ]
    return top, bottom, [int(x) for x in starts], [int(x) for x in rights], gutters


def _persistent_rule_mask(body_ink: np.ndarray, reference: float) -> np.ndarray:
    """Find narrow X columns that behave like printed vertical rules.

    A rule remains dark through most vertical body blocks; ordinary glyph strokes
    do not.  The returned mask is used only while estimating text-column edges,
    so the rule may remain visible in all later source/crop operations.
    """
    if body_ink.size == 0:
        return np.zeros(body_ink.shape[1] if body_ink.ndim == 2 else 0, dtype=bool)
    blocks = [
        block for block in np.array_split(
            body_ink, min(20, max(5, body_ink.shape[0] // max(24, round(reference * 2.5)))), axis=0
        ) if block.size
    ]
    density = body_ink.mean(axis=0)
    persistence = np.vstack([block.mean(axis=0) >= 0.18 for block in blocks]).mean(axis=0)
    rule = (density >= 0.34) & (persistence >= 0.72)
    # Expand only enough to cover antialiasing/scan blur around the printed rule.
    pad = max(1, round(reference * 0.08))
    expanded = rule.copy()
    for shift in range(1, pad + 1):
        expanded[shift:] |= rule[:-shift]
        expanded[:-shift] |= rule[shift:]
    return expanded


def _robust_first_text_x(
    region: np.ndarray,
    reference: float,
) -> int | None:
    if region.size == 0:
        return None
    firsts: list[int] = []
    minimum_row_ink = max(2, round(reference * 0.16))
    for row in region:
        xs = np.flatnonzero(row)
        if xs.size < minimum_row_ink:
            continue
        firsts.append(int(xs[0]))
    if len(firsts) < 6:
        return None
    values = np.asarray(firsts, dtype=float)
    # Low quantile recovers the designed left text edge while ignoring a few
    # isolated specks.  It is intentionally not the absolute minimum.
    return int(round(float(np.quantile(values, 0.12))))


def _refine_column_text_edges(
    page_ink: np.ndarray,
    top: int,
    bottom: int,
    starts: list[int],
    rights: list[int],
    reference: float,
) -> tuple[list[int], list[int], list[int]]:
    """Convert rough slots into true text starts/ends, ignoring divider rules."""
    if not starts:
        return starts, rights, []
    body = page_ink[max(0, top):max(top + 1, bottom), :].copy()
    rule_mask = _persistent_rule_mask(body, reference)
    if rule_mask.size:
        body[:, rule_mask] = False

    refined = list(starts)
    for index in range(len(starts)):
        if index == 0:
            search_left = max(0, int(starts[index]) - round(reference * 1.5))
        else:
            # Anything before the previous observed text-right is either its
            # trailing text or the gutter; it cannot be the next text-column edge.
            search_left = max(
                0,
                int(rights[index - 1]) + max(1, round(reference * 0.20)),
            )
        search_right = min(
            body.shape[1],
            max(search_left + 2, int(rights[index]) + round(reference * 1.5)),
        )
        if search_right <= search_left:
            continue
        local = _robust_first_text_x(
            body[:, search_left:search_right], reference,
        )
        if local is not None:
            refined[index] = search_left + int(local)

    # Preserve observed text-rights, but guarantee sane ordering after refined
    # starts.  Gutter is the whitespace from text-right to next text-start; a
    # vertical rule inside that whitespace cannot change its semantic width.
    fixed_rights: list[int] = []
    for index, start in enumerate(refined):
        right = int(rights[index]) if index < len(rights) else start + 1
        if index + 1 < len(refined):
            right = min(right, int(refined[index + 1]) - 1)
        fixed_rights.append(max(int(start) + 1, right))
    gutters = [
        max(0, int(refined[i + 1]) - int(fixed_rights[i]))
        if i + 1 < len(refined) else 0
        for i in range(len(refined))
    ]
    return refined, fixed_rights, gutters


def _leading_strip_width(column_width: int, seed_height: float) -> int:
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
    anchors = [
        part for part in _component_runs(line, reference)
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
        py0 = max(0, int(y0) - round(reference * 0.10))
        py1 = min(ink.shape[0], int(y1) + round(reference * 0.10))
        px0 = max(0, int(anchor_x) - round(reference * 0.05))
        px1 = min(ink.shape[1], int(anchor_x) + round(reference * 0.78))
        patch = ink[py0:py1, px0:px1].copy()
    return LayoutLine(
        column=int(column),
        y0=int(y0),
        y1=int(y1),
        first_x=first_x,
        anchor_x=anchor_x,
        anchor_width=anchor_width,
        anchor_height=anchor_height,
        gap_before=max(0, int(y0) - int(previous_end)),
        patch=patch,
        has_small_prefix=has_small_prefix,
    )


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
        deviations = np.asarray(
            [abs(float(item.anchor_x or 0) - center) for item in cluster], dtype=float
        )
        q90 = float(np.quantile(deviations, 0.90)) if deviations.size else 0.0
        mode_tolerance = max(
            reference * 0.14,
            min(reference * 0.34, q90 + reference * 0.08),
        )
        modes.append(IndentMode(
            center=center,
            tolerance=float(mode_tolerance),
            lines=list(cluster),
            shape_consensus=_shape_consensus(cluster),
        ))
    return sorted(modes, key=lambda mode: mode.center)


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

    # The user-provided semantic prior resolves the otherwise ambiguous polarity.
    body = (
        min(stable, key=lambda item: item.center)
        if indent_type == "headword"
        else max(stable, key=lambda item: item.center)
    )
    body.role = "body"
    column.body_mode = body

    sign = 1.0 if indent_type == "headword" else -1.0
    entries: list[IndentMode] = []
    for mode in modes:
        if mode is body:
            continue
        separation = sign * (float(mode.center) - float(body.center))
        if reference * 0.42 <= separation <= reference * 5.0 and mode.support >= 2:
            mode.role = "entry"
            entries.append(mode)
    column.entry_modes = entries


def _ordinary_pitch(columns: list[ColumnDesign], reference: float) -> float:
    steps: list[float] = []
    for column in columns:
        ys = sorted(
            line.y0 for line in column.lines
            if reference * 0.55 <= line.height <= reference * 1.45
        )
        steps.extend(
            float(b - a) for a, b in zip(ys, ys[1:])
            if reference * 0.75 <= b - a <= reference * 2.4
        )
    return (
        float(np.median(np.asarray(steps, dtype=float)))
        if steps else float(reference * 1.25)
    )


def _ordinary_char_width(columns: list[ColumnDesign], reference: float) -> float:
    widths = [
        float(line.anchor_width)
        for column in columns
        for line in column.lines
        if reference * 0.22 <= line.anchor_width <= reference * 1.45
        and reference * 0.55 <= line.anchor_height <= reference * 1.35
    ]
    if len(widths) >= 5:
        return float(np.median(np.asarray(widths, dtype=float)))
    return float(reference)


def _group_large_fragments(
    boxes: list[tuple[int, int, int, int, int]],
    reference: float,
) -> list[tuple[int, int, int, int, int]]:
    """Group only nearby oversized fragments; normal text never enters."""
    candidates: list[list[int]] = []
    for x0, y0, x1, y1, area in boxes:
        width, height = x1 - x0, y1 - y0
        if area < reference * reference * 0.025:
            continue
        if width > reference * 3.9 or height > reference * 3.9:
            continue
        if not (
            height >= reference * 1.08
            or (width >= reference * 1.05 and height >= reference * 0.62)
        ):
            continue
        candidates.append([int(x0), int(y0), int(x1), int(y1), int(area)])

    changed = True
    while changed:
        changed = False
        output: list[list[int]] = []
        while candidates:
            current = candidates.pop(0)
            rest: list[list[int]] = []
            for other in candidates:
                hgap = max(0, max(current[0], other[0]) - min(current[2], other[2]))
                vgap = max(0, max(current[1], other[1]) - min(current[3], other[3]))
                x_overlap = max(0, min(current[2], other[2]) - max(current[0], other[0]))
                y_overlap = max(0, min(current[3], other[3]) - max(current[1], other[1]))
                vertical_neighbors = (
                    x_overlap >= reference * 0.20 and vgap <= reference * 0.34
                )
                horizontal_neighbors = (
                    y_overlap >= reference * 0.28 and hgap <= reference * 0.55
                )
                if vertical_neighbors or horizontal_neighbors:
                    current = [
                        min(current[0], other[0]), min(current[1], other[1]),
                        max(current[2], other[2]), max(current[3], other[3]),
                        current[4] + other[4],
                    ]
                    changed = True
                else:
                    rest.append(other)
            candidates = rest
            output.append(current)
        candidates = output
    return [tuple(item) for item in candidates]


def _display_heads(
    column: ColumnDesign,
    column_ink: np.ndarray,
    reference: float,
    indent_type: str,
) -> list[DisplayHead]:
    body = column.body_mode
    if body is None or column_ink.size == 0:
        return []
    sign = 1.0 if indent_type == "headword" else -1.0
    raw = _components(column_ink)
    groups = _group_large_fragments(raw, reference)

    # Add tall visual-block candidates. This catches a clean display glyph even
    # when its internal strokes fragment into components that individually look
    # only ordinary-sized. Fill only tiny internal holes, never normal line gaps.
    active = column_ink.sum(axis=1) >= max(2, round(column_ink.shape[1] * 0.004))
    joined = _fill_short_gaps(active, max(1, round(reference * 0.22)))
    for y0, y1 in _runs(joined):
        if not (reference * 1.35 <= y1 - y0 <= reference * 3.9):
            continue
        roi = column_ink[y0:y1]
        xs = np.flatnonzero(roi.any(axis=0))
        if xs.size:
            x0, x1 = int(xs[0]), int(xs[-1] + 1)
            groups.append((x0, int(y0), x1, int(y1), int(roi.sum())))

    result: list[DisplayHead] = []
    for x0, y0, x1, y1, area in groups:
        width, height = int(x1) - int(x0), int(y1) - int(y0)
        if area < reference * reference * 0.10:
            continue
        if not (reference * 1.35 <= height <= reference * 3.9):
            continue
        if not (reference * 0.58 <= width <= reference * 3.9):
            continue
        aspect = height / float(max(1, width))
        if not 0.40 <= aspect <= 3.1:
            continue
        separation = sign * (float(x0) - float(body.center))
        if not (reference * 0.10 <= separation <= reference * 5.3):
            continue
        result.append(DisplayHead(
            column=column.index,
            x0=int(x0), y0=int(y0), x1=int(x1), y1=int(y1),
        ))

    result.sort(key=lambda head: (head.y0, head.x0, head.height * head.width))
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


def _page_regions(
    settings: AppSettings,
    page_index: int,
    source_size: tuple[int, int],
    transform: LayoutTransform,
    body_box_canonical: Box,
) -> PageRegions:
    width, height = source_size
    regions: dict[str, PageRegion | None] = {"header": None, "footer": None, "side": None}

    header_mode = str(getattr(settings, "profile_header_mode", "auto") or "auto")
    if header_mode == "present":
        amount = round(height * max(0.0, min(35.0, float(settings.profile_header_percent))) / 100.0)
        box = (0, 0, width, amount)
        regions["header"] = PageRegion("header", box, transform.source_box_to_canonical(box, source_size), "configured")
    elif body_box_canonical[1] > 0:
        canonical = (0, 0, transform.canonical_size(source_size)[0], body_box_canonical[1])
        regions["header"] = PageRegion("header", transform.canonical_box_to_source(canonical, source_size), canonical, "inferred")

    footer_mode = str(getattr(settings, "profile_footer_mode", "auto") or "auto")
    if footer_mode == "present":
        amount = round(height * max(0.0, min(35.0, float(settings.profile_footer_percent))) / 100.0)
        box = (0, max(0, height - amount), width, height)
        regions["footer"] = PageRegion("footer", box, transform.source_box_to_canonical(box, source_size), "configured")

    side = excluded_source_side(settings, page_index)
    if side is not None:
        pct = excluded_source_side_percent(settings, page_index)
        amount = round(width * pct / 100.0)
        box = (0, 0, amount, height) if side == "left" else (max(0, width - amount), 0, width, height)
        regions["side"] = PageRegion("side", box, transform.source_box_to_canonical(box, source_size), "configured")

    body_source = transform.canonical_box_to_source(body_box_canonical, source_size)
    body = PageRegion("body", body_source, body_box_canonical, "inferred")
    return PageRegions(
        body=body,
        header=regions["header"],
        footer=regions["footer"],
        side=regions["side"],
    )


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

    # Column starts are a typographic property, not "the first dark thing in a
    # slot". Refine them from repeated text occupancy after removing persistent
    # vertical rules from this geometry-only view.
    starts, rights, gutters = _refine_column_text_edges(
        page_ink, top, bottom, starts, rights, seed,
    )

    raw_runs: list[list[tuple[int, int]]] = []
    strips: list[np.ndarray] = []
    for left, right in zip(starts, rights):
        left = max(0, min(canonical.width - 1, int(left)))
        right = max(left + 1, min(canonical.width, int(right)))
        strip_width = _leading_strip_width(right - left, seed)
        strip = page_ink[top:bottom, left:left + strip_width]
        strips.append(strip)
        raw_runs.append(_line_runs(strip, seed))

    reference = _robust_normal_height(raw_runs, seed)
    # Re-run text-edge refinement with the measured ordinary line scale.
    starts, rights, gutters = _refine_column_text_edges(
        page_ink, top, bottom, starts, rights, reference,
    )
    strips = []
    raw_runs = []
    for left, right in zip(starts, rights):
        strip_width = _leading_strip_width(max(1, right - left), reference)
        strip = page_ink[top:bottom, left:left + strip_width]
        strips.append(strip)
        raw_runs.append(_line_runs(strip, reference))

    indent_type = _indent_type(settings)
    columns: list[ColumnDesign] = []
    for index, (left, right, gutter, strip, runs) in enumerate(
        zip(starts, rights, gutters, strips, raw_runs)
    ):
        column = ColumnDesign(
            index=index, left=int(left), right=int(right), gutter_after=int(gutter)
        )
        previous_end = 0
        for y0, y1 in runs:
            line = _line_feature(index, strip, y0, y1, reference, previous_end)
            previous_end = max(previous_end, int(y1))
            if line is not None and reference * 0.45 <= line.height <= reference * 1.55:
                column.lines.append(line)
        column.indent_modes = _cluster_indent_modes(column.lines, reference)
        _choose_semantic_modes(column, indent_type, reference)
        columns.append(column)

    # Page-level design transfer: sparse columns inherit a repeatedly proven
    # entry offset from their siblings.  They do not need two local occurrences.
    normalized_entry_offsets: list[float] = []
    sign = 1.0 if indent_type == "headword" else -1.0
    for column in columns:
        if column.body_mode is None:
            continue
        for mode in column.entry_modes:
            normalized_entry_offsets.append(
                sign * (mode.center - column.body_mode.center) / max(1.0, reference)
            )
    page_entry_offset = (
        float(np.median(np.asarray(normalized_entry_offsets, dtype=float)))
        if normalized_entry_offsets else None
    )
    if page_entry_offset is not None:
        for column in columns:
            body = column.body_mode
            if body is None:
                continue
            predicted = body.center + sign * page_entry_offset * reference
            existing = {id(line) for mode in column.entry_modes for line in mode.lines}
            sparse = [
                line for line in column.lines
                if id(line) not in existing
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

    pitch = _ordinary_pitch(columns, reference)
    char_width = _ordinary_char_width(columns, reference)
    display_heads: list[DisplayHead] = []
    for column, strip in zip(columns, strips):
        display_heads.extend(_display_heads(column, strip, reference, indent_type))

    display_width = (
        float(np.median([head.width for head in display_heads]))
        if display_heads else 0.0
    )
    display_height = (
        float(np.median([head.height for head in display_heads]))
        if display_heads else 0.0
    )

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
    regions = _page_regions(
        settings,
        page_index,
        source.size,
        transform,
        (int(body_left), int(top), int(body_right), int(bottom)),
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
        body_top=int(top),
        body_bottom=int(bottom),
        columns=columns,
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
    return int(previous) + max(1, gap // 2)


def _source_boundary_entry(
    layout: DictionaryPageLayout,
    column: ColumnDesign,
    canonical_y: int,
    *,
    kind: str,
    confidence: float,
) -> Entry:
    source_x, source_y = layout.transform.canonical_to_source_point(
        int(column.left),
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
                line.role = (
                    "body"
                    if column.body_mode and line in column.body_mode.lines
                    else "unknown"
                )
                continue
            line.role = "entry"
            local_y = _boundary_before(column.lines, line.y0, reference)
            entry = _source_boundary_entry(
                layout,
                column,
                local_y,
                kind="ORDINARY_PAGE_DESIGN_ENTRY",
                confidence=0.97 if line.has_small_prefix else 0.96,
            )
            if page_sections and not any(
                int(section.top_v) <= entry.y < int(section.bottom_v)
                for section in page_sections
            ):
                continue
            entries.append(entry)

    for head in layout.display_heads:
        column = layout.columns[head.column]
        local_y = _boundary_before(column.lines, head.y0, reference)
        entry = _source_boundary_entry(
            layout,
            column,
            local_y,
            kind="ORDINARY_PAGE_DESIGN_DISPLAY_HEAD",
            confidence=0.98,
        )
        if page_sections and not any(
            int(section.top_v) <= entry.y < int(section.bottom_v)
            for section in page_sections
        ):
            continue
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
    entries = (
        infer_entry_boundaries(layout, page_sections=page_sections)
        if layout.reliable else []
    )
    return LayoutDetectionResult(entries=entries, layout=layout)
