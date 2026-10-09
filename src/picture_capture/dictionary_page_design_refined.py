from __future__ import annotations

"""Second-stage refinement for OCR-free dictionary page-design inference.

The base page model deliberately records *all* stable indentation modes.  This
module assigns entry semantics at the next abstraction level.  A dictionary
page can contain several legitimate indents (quotation, continuation, sense,
example, entry, ...); therefore "not body" must never mean "entry".

The refinement does four things:

1. groups signed indent offsets across columns into page-level families;
2. selects one typographically coherent entry family instead of accepting every
   non-body indent;
3. models the entry lane as x(y) when the scan bends or drifts; and
4. looks one ordinary-line height beyond the logical body at the top/bottom so
   first/last entries are not lost merely because their ink crosses the crop.

No OCR or character recognition is used.  Repeated leading-shape evidence is
only a typography cue (for example, a repeated bracket glyph), not a decoded
symbol.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from . import dictionary_page_design as base
from .layout_detection import analysis_ink_mask
from .models import AppSettings, Entry
from .ordinary_visual import _patch_similarity
from .profile_semantics import page_template_analysis_image


@dataclass(slots=True)
class EntryIndentFamily:
    offset_ratio: float
    tolerance_ratio: float
    support: int
    column_support: int
    shape_consensus: float
    modes: list[tuple[base.ColumnDesign, base.IndentMode]]


@dataclass(slots=True)
class _LaneModel:
    intercept: float
    slope: float = 0.0

    def x_at(self, y: float) -> float:
        return float(self.intercept + self.slope * y)


def _sign(layout: base.DictionaryPageLayout) -> float:
    return 1.0 if layout.indent_type == "headword" else -1.0


def _mode_offset_ratio(
    column: base.ColumnDesign,
    mode: base.IndentMode,
    reference: float,
    sign: float,
) -> float | None:
    body = column.body_mode
    if body is None:
        return None
    return sign * (float(mode.center) - float(body.center)) / max(1.0, reference)


def _group_indent_families(
    layout: base.DictionaryPageLayout,
) -> list[EntryIndentFamily]:
    reference = max(1.0, float(layout.ordinary_line_height))
    sign = _sign(layout)
    observations: list[tuple[float, base.ColumnDesign, base.IndentMode]] = []
    for column in layout.columns:
        for mode in column.indent_modes:
            if mode is column.body_mode:
                continue
            offset = _mode_offset_ratio(column, mode, reference, sign)
            if offset is None or not (0.28 <= offset <= 5.0):
                continue
            observations.append((float(offset), column, mode))

    groups: list[list[tuple[float, base.ColumnDesign, base.IndentMode]]] = []
    # A fairly wide family radius is intentional.  On curved scans one printed
    # lane can split into several scalar-X clusters even though its semantic
    # offset is unchanged.  The 0.55h radius still leaves the common 0.5h
    # continuation indent well separated from a ~2h entry indent.
    family_radius = 0.55
    for item in sorted(observations, key=lambda value: value[0]):
        target: list[tuple[float, base.ColumnDesign, base.IndentMode]] | None = None
        for group in groups:
            center = float(np.median([value[0] for value in group]))
            if abs(item[0] - center) <= family_radius:
                target = group
                break
        if target is None:
            groups.append([item])
        else:
            target.append(item)

    result: list[EntryIndentFamily] = []
    for group in groups:
        modes = [(column, mode) for _offset, column, mode in group]
        lines = [line for _column, mode in modes for line in mode.lines]
        offsets = np.asarray([value[0] for value in group], dtype=float)
        center = float(np.median(offsets))
        deviation = np.abs(offsets - center)
        q90 = float(np.quantile(deviation, 0.90)) if deviation.size else 0.0
        result.append(EntryIndentFamily(
            offset_ratio=center,
            tolerance_ratio=max(0.24, min(0.62, q90 + 0.20)),
            support=sum(mode.support for _column, mode in modes),
            column_support=len({column.index for column, _mode in modes}),
            shape_consensus=base._shape_consensus(lines),
            modes=modes,
        ))
    return sorted(result, key=lambda family: family.offset_ratio)


def _choose_entry_family(
    families: list[EntryIndentFamily],
) -> EntryIndentFamily | None:
    """Choose one entry family; intermediate indents remain non-entry layout.

    A shallow family can still be an entry family when its leading structure is
    highly repetitive.  Without such structure, the family must be both deeper
    and well supported.  This prevents quotation/continuation indents from being
    promoted merely because they occur repeatedly.
    """
    viable = [family for family in families if family.support >= 2]
    if not viable:
        return None

    structural = [
        family for family in viable
        if family.shape_consensus >= 0.50 and family.offset_ratio >= 0.38
    ]
    deep = [
        family for family in viable
        if family.offset_ratio >= 1.15
        and (
            family.column_support >= 2
            or family.support >= 3
            or family.shape_consensus >= 0.42
        )
    ]
    pool = structural or deep
    if not pool:
        return None

    def score(family: EntryIndentFamily) -> float:
        support_term = min(1.0, np.log1p(float(family.support)) / np.log(8.0))
        return (
            2.2 * float(family.shape_consensus)
            + 0.42 * min(3.2, float(family.offset_ratio))
            + 0.30 * float(support_term)
            + 0.18 * min(2, int(family.column_support))
        )

    return max(pool, key=score)


def _companion_families(
    families: list[EntryIndentFamily],
    primary: EntryIndentFamily,
) -> list[EntryIndentFamily]:
    """Keep nearby pieces of the same curved entry lane, not shallow indents."""
    selected = [primary]
    for family in families:
        if family is primary:
            continue
        delta = abs(float(family.offset_ratio) - float(primary.offset_ratio))
        if delta > max(0.62, primary.tolerance_ratio + 0.18):
            continue
        if family.offset_ratio < max(0.38, primary.offset_ratio - 0.78):
            continue
        if family.support >= 2 or family.shape_consensus >= 0.36:
            selected.append(family)
    return selected


def _family_lines(families: list[EntryIndentFamily]) -> list[base.LayoutLine]:
    return [
        line
        for family in families
        for _column, mode in family.modes
        for line in mode.lines
    ]


def _lane_for_column(
    layout: base.DictionaryPageLayout,
    column: base.ColumnDesign,
    family: EntryIndentFamily,
    selected_modes: list[base.IndentMode],
) -> _LaneModel:
    reference = max(1.0, float(layout.ordinary_line_height))
    sign = _sign(layout)
    observations = [
        (float(line.y0), float(line.anchor_x))
        for mode in selected_modes
        for line in mode.lines
        if line.anchor_x is not None
    ]
    if len(observations) >= 3:
        ys = np.asarray([item[0] for item in observations], dtype=float)
        xs = np.asarray([item[1] for item in observations], dtype=float)
        if float(np.ptp(ys)) >= reference * 3.0:
            slope, intercept = np.polyfit(ys, xs, 1)
            # A scan may bend, but a printed lane cannot legitimately walk by
            # several characters over one page.  Clamp pathological fits.
            max_slope = reference * 0.90 / max(reference * 8.0, float(np.ptp(ys)))
            slope = float(np.clip(slope, -max_slope, max_slope))
            intercept = float(np.median(xs - slope * ys))
            return _LaneModel(intercept=intercept, slope=slope)
    body_center = float(column.body_mode.center) if column.body_mode is not None else 0.0
    return _LaneModel(
        intercept=body_center + sign * float(family.offset_ratio) * reference,
        slope=0.0,
    )


def _looks_like_family_shape(
    line: base.LayoutLine,
    prototypes: list[np.ndarray],
    family_consensus: float,
) -> bool:
    if family_consensus < 0.46:
        return True
    if not line.patch.size or not prototypes:
        return False
    return max(
        (_patch_similarity(proto, line.patch) for proto in prototypes),
        default=0.0,
    ) >= 0.40


def refine_indent_semantics(
    layout: base.DictionaryPageLayout,
) -> EntryIndentFamily | None:
    """Replace binary non-body=>entry semantics with page-level indent families."""
    reference = max(1.0, float(layout.ordinary_line_height))
    families = _group_indent_families(layout)
    primary = _choose_entry_family(families)

    # Clear the base module's permissive semantic assignment, including sparse
    # transfer modes that were not part of the measured indent distribution.
    for column in layout.columns:
        for mode in column.indent_modes:
            mode.role = "body" if mode is column.body_mode else "other_indent"
        column.entry_modes = []
    if primary is None:
        return None

    selected_families = _companion_families(families, primary)
    selected_mode_ids = {
        id(mode)
        for family in selected_families
        for _column, mode in family.modes
    }
    all_selected_lines = _family_lines(selected_families)
    prototypes = [line.patch for line in all_selected_lines if line.patch.size]
    family_consensus = base._shape_consensus(all_selected_lines)

    for column in layout.columns:
        selected_modes = [
            mode for mode in column.indent_modes if id(mode) in selected_mode_ids
        ]
        for mode in selected_modes:
            mode.role = "entry"
        column.entry_modes = list(selected_modes)

        # Recover sparse members of the same lane.  The target is x(y), not one
        # page-wide scalar X, so mild curvature does not split a printed lane.
        if column.body_mode is None:
            continue
        lane = _lane_for_column(layout, column, primary, selected_modes)
        assigned = {id(line) for mode in selected_modes for line in mode.lines}
        sparse: list[base.LayoutLine] = []
        for line in column.lines:
            if id(line) in assigned or line.anchor_x is None:
                continue
            if abs(float(line.anchor_x) - lane.x_at(float(line.y0))) > reference * 0.38:
                continue
            if not _looks_like_family_shape(line, prototypes, family_consensus):
                continue
            sparse.append(line)
        if sparse:
            mode = base.IndentMode(
                center=float(np.median([float(line.anchor_x or 0) for line in sparse])),
                tolerance=reference * 0.38,
                lines=sparse,
                shape_consensus=base._shape_consensus(sparse),
                role="entry",
            )
            column.entry_modes.append(mode)

    # Return a family whose diagnostics reflect all selected pieces.
    selected_modes_flat = [
        (column, mode)
        for column in layout.columns
        for mode in column.entry_modes
    ]
    selected_lines = [line for _column, mode in selected_modes_flat for line in mode.lines]
    return EntryIndentFamily(
        offset_ratio=float(primary.offset_ratio),
        tolerance_ratio=max(family.tolerance_ratio for family in selected_families),
        support=len(selected_lines),
        column_support=len({column.index for column, _mode in selected_modes_flat}),
        shape_consensus=base._shape_consensus(selected_lines),
        modes=selected_modes_flat,
    )


def _entry_from_absolute_boundary(
    layout: base.DictionaryPageLayout,
    column: base.ColumnDesign,
    canonical_y: int,
    issue_type: str,
    confidence: float,
) -> Entry:
    x, y = layout.transform.canonical_to_source_point(
        int(column.left), int(canonical_y), layout.source_size,
    )
    return Entry(
        word="",
        x=int(x),
        y=int(y),
        confidence=float(confidence),
        ocr_source="ordinary_page_design",
        issue_type=issue_type,
    )


def _existing_boundary_near(
    entries: list[Entry],
    candidate: Entry,
    reference: float,
) -> bool:
    return any(
        abs(int(entry.y) - int(candidate.y)) <= reference * 0.48
        and abs(int(entry.x) - int(candidate.x)) <= reference * 1.2
        for entry in entries
    )


def _guard_band_entries(
    image: Image.Image,
    settings: AppSettings,
    layout: base.DictionaryPageLayout,
    family: EntryIndentFamily | None,
    existing: list[Entry],
    *,
    page_index: int,
    ops: base.LayoutPrimitiveOps | None = None,
) -> list[Entry]:
    """Recover first/last entry blocks whose ink crosses the logical body edge."""
    ops = base.current_layout_ops() if ops is None else ops
    reference = max(1.0, float(layout.ordinary_line_height))
    guard = max(4, round(reference * 1.15))
    source = base.normalize_page_rgb(image)
    template = page_template_analysis_image(source, settings, page_index)
    canonical = layout.transform.canonical_image_for_analysis(template)
    effective = base.effective_page_settings(settings, source.size, page_index)
    page_ink = analysis_ink_mask(
        np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8), effective
    )
    analysis_top = max(0, int(layout.body_top) - guard)
    analysis_bottom = min(canonical.height, int(layout.body_bottom) + guard)
    if analysis_bottom <= analysis_top:
        return []

    family_lines = _family_lines([family]) if family is not None else []
    prototypes = [line.patch for line in family_lines if line.patch.size]
    family_consensus = base._shape_consensus(family_lines)
    recovered: list[Entry] = []

    for column in layout.columns:
        if column.body_mode is None:
            continue
        width = max(1, int(column.right) - int(column.left))
        lead = base._leading_width(width, reference)
        strip = page_ink[
            analysis_top:analysis_bottom,
            int(column.left):min(canonical.width, int(column.left) + lead),
        ]
        if strip.size == 0:
            continue

        selected_modes = list(column.entry_modes)
        lane = (
            _lane_for_column(layout, column, family, selected_modes)
            if family is not None
            else None
        )
        runs = ops.line_runs(strip, reference)
        previous_end = 0
        features: list[tuple[base.LayoutLine, int, int]] = []
        for y0, y1 in runs:
            line = ops.line_feature(
                column.index, strip, y0, y1, reference, previous_end,
            )
            previous_end = max(previous_end, y1)
            if line is None or not (reference * 0.42 <= line.height <= reference * 1.65):
                continue
            absolute_y0 = analysis_top + int(y0)
            absolute_y1 = analysis_top + int(y1)
            near_top = absolute_y0 <= int(layout.body_top) + reference * 0.72
            near_bottom = absolute_y1 >= int(layout.body_bottom) - reference * 0.72
            if near_top or near_bottom:
                features.append((line, absolute_y0, absolute_y1))

        if lane is not None:
            for line, absolute_y0, _absolute_y1 in features:
                if line.anchor_x is None:
                    continue
                # Lane model uses body-local y; convert from canonical y.
                local_y = float(absolute_y0 - int(layout.body_top))
                if abs(float(line.anchor_x) - lane.x_at(local_y)) > reference * 0.40:
                    continue
                if not _looks_like_family_shape(line, prototypes, family_consensus):
                    continue

                if absolute_y0 <= int(layout.body_top) + reference * 0.72:
                    boundary = int(layout.body_top)
                else:
                    previous = max(
                        (
                            int(layout.body_top) + int(other.y1)
                            for other in column.lines
                            if int(layout.body_top) + int(other.y1) <= absolute_y0
                        ),
                        default=max(int(layout.body_top), absolute_y0 - round(reference)),
                    )
                    gap = max(1, absolute_y0 - previous)
                    boundary = previous + max(1, gap // 2)
                boundary = max(int(layout.body_top), min(int(layout.body_bottom) - 1, boundary))
                item = _entry_from_absolute_boundary(
                    layout, column, boundary,
                    "ORDINARY_PAGE_DESIGN_GUARD_ENTRY", 0.965,
                )
                if not _existing_boundary_near(existing + recovered, item, reference):
                    recovered.append(item)

        # Display-size heads are a separate typography level.  Re-run that
        # detector on the guard-extended strip so a large glyph clipped by the
        # logical body boundary can still be seen as a complete component.
        guard_heads = base._display_heads(column, strip, reference, layout.indent_type)
        for head in guard_heads:
            absolute_y0 = analysis_top + int(head.y0)
            absolute_y1 = analysis_top + int(head.y1)
            if not (
                absolute_y0 <= int(layout.body_top) + reference * 0.78
                or absolute_y1 >= int(layout.body_bottom) - reference * 0.78
            ):
                continue
            if absolute_y0 <= int(layout.body_top) + reference * 0.78:
                boundary = int(layout.body_top)
            else:
                previous = max(
                    (
                        int(layout.body_top) + int(other.y1)
                        for other in column.lines
                        if int(layout.body_top) + int(other.y1) <= absolute_y0
                    ),
                    default=max(int(layout.body_top), absolute_y0 - round(reference)),
                )
                boundary = previous + max(1, (absolute_y0 - previous) // 2)
            boundary = max(int(layout.body_top), min(int(layout.body_bottom) - 1, boundary))
            item = _entry_from_absolute_boundary(
                layout, column, boundary,
                "ORDINARY_PAGE_DESIGN_GUARD_DISPLAY_HEAD", 0.98,
            )
            item.ocr_single_cjk = True
            item.ocr_oversized_cjk = True
            item.ocr_visual_run_height = float(head.height)
            item.ocr_line_height_reference = reference
            if not _existing_boundary_near(existing + recovered, item, reference):
                recovered.append(item)

    return recovered


def _deduplicate_reading_order(
    layout: base.DictionaryPageLayout,
    entries: list[Entry],
) -> list[Entry]:
    reference = max(1.0, float(layout.ordinary_line_height))
    observations: list[tuple[int, int, int, Entry]] = []
    for entry in entries:
        u, v = layout.transform.source_to_canonical_point(
            int(entry.x), int(entry.y), layout.source_size,
        )
        column = min(
            range(len(layout.columns)),
            key=lambda index: abs(int(layout.columns[index].left) - int(u)),
            default=0,
        ) if layout.columns else 0
        observations.append((column, int(v), int(u), entry))
    observations.sort(key=lambda item: (item[0], item[1], item[2]))

    result: list[Entry] = []
    last_by_column: dict[int, int] = {}
    for column, v, _u, entry in observations:
        if column in last_by_column and abs(v - last_by_column[column]) <= reference * 0.38:
            continue
        result.append(entry)
        last_by_column[column] = v
    return result


def detect_entries_from_page_design(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int = 0,
    page_sections: list[Any] | None = None,
    ops: base.LayoutPrimitiveOps | None = None,
) -> base.LayoutDetectionResult:
    """Infer page design, refine indent families, then derive boundaries."""
    layout = base.infer_dictionary_page_layout(
        image, settings, page_index=page_index,
        **({"ops": ops} if ops is not None else {}),
    )
    family = refine_indent_semantics(layout)
    if not layout.reliable:
        return base.LayoutDetectionResult(entries=[], layout=layout)

    entries = base.infer_entry_boundaries(layout, page_sections=page_sections)
    entries.extend(_guard_band_entries(
        image, settings, layout, family, entries, page_index=page_index,
        **({"ops": ops} if ops is not None else {}),
    ))
    entries = _deduplicate_reading_order(layout, entries)
    if family is None:
        layout.reason += "; refined_entry_family=none"
    else:
        layout.reason += (
            f"; refined_entry_family={family.offset_ratio:.2f}h"
            f" support={family.support} columns={family.column_support}"
            f" shape={family.shape_consensus:.2f}"
        )
    return base.LayoutDetectionResult(entries=entries, layout=layout)


def layout_diagnostics(layout: base.DictionaryPageLayout) -> dict[str, Any]:
    """Extend base diagnostics with multi-indent semantic information."""
    data = base.layout_diagnostics(layout)
    reference = max(1.0, float(layout.ordinary_line_height))
    sign = _sign(layout)
    entry_offsets = [
        sign * (float(mode.center) - float(column.body_mode.center)) / reference
        for column in layout.columns if column.body_mode is not None
        for mode in column.entry_modes
    ]
    other_offsets = [
        sign * (float(mode.center) - float(column.body_mode.center)) / reference
        for column in layout.columns if column.body_mode is not None
        for mode in column.indent_modes
        if mode is not column.body_mode and mode.role != "entry"
    ]
    data["indent_semantics"] = {
        "entry_offset_ratios": entry_offsets,
        "entry_offset_ratio_median": (
            float(np.median(entry_offsets)) if entry_offsets else None
        ),
        "other_indent_offset_ratios": other_offsets,
        "principle": "indent mode is layout evidence; only the selected family is entry",
    }
    return data
