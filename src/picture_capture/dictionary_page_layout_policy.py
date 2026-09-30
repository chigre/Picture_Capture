from __future__ import annotations

"""Policy-aware dictionary page-design inference.

The dictionary has one project-level template, while each scan is a page
instance.  Existing ``ordinary_auto_layout`` controls which physical template
fields may be replaced by measurements from the current page.  Fields that are
not selected remain fixed project/Profile priors.

This is intentionally different from indentation-family analysis.  Body/entry
indent families are always measured in each page's *local column coordinates*,
because scanner translation, skew and book curvature change absolute X without
changing the underlying typesetting semantics.  The explicit headword/body
indent choice therefore controls semantic direction, not whether local evidence
is observed.

Per-page adaptation stays OCR-free.  In particular, automatic ``manual_x`` is a
registration of the current scan against the Project template; it is not a
fresh search for whichever text lane has the most ink.  This prevents an inward
body lane from becoming the physical column edge on body-indented dictionaries.
"""

from dataclasses import replace
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from . import dictionary_page_design as base
from . import dictionary_page_design_refined as refined
from .layout_detection import analysis_ink_mask, _projection_layout_estimate, LayoutEstimate
from .models import AppSettings
from .page_x_registration import register_page_manual_x


AUTO_LAYOUT_FIELDS: tuple[tuple[str, str], ...] = (
    ("columns", "ordinary_auto_columns"),
    ("start_y", "ordinary_auto_start_y"),
    ("manual_x", "ordinary_auto_manual_x"),
    ("column_width", "ordinary_auto_column_width"),
    ("gutter", "ordinary_auto_gutter"),
    ("character_height", "ordinary_auto_character_height"),
    ("row_padding", "ordinary_auto_row_padding"),
)


def _auto_enabled(settings: AppSettings, switch: str) -> bool:
    return bool(getattr(settings, "ordinary_auto_layout", False)) and bool(
        getattr(settings, switch, False)
    )


def resolve_page_layout_policy(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int = 0,
) -> tuple[AppSettings, LayoutEstimate | None, dict[str, int]]:
    """Resolve the existing master/per-field layout policy for one page.

    The project settings object is never mutated.  When the master switch is
    off no per-page geometry detector is run.  When it is on, one OCR-free
    projection estimate is made and only explicitly selected fields replace
    their project-level values.

    ``manual_x`` is special only in *how* its selected value is measured: the
    projection estimate is treated as an observation, while the final value is
    a semantic-aware page translation of the Project template.  This preserves
    the meaning of "首栏X自动" without allowing a dominant inward body lane to
    redefine the column origin.
    """
    current = replace(settings)
    if not bool(getattr(current, "ordinary_auto_layout", False)):
        current.manual_columns = False
        return current, None, {}

    detector_settings = replace(current)
    if bool(getattr(current, "ordinary_auto_columns", False)):
        detector_settings.layout_columns_policy = "detect"

    # Use the same masked/canonical page domain as the page-design model itself.
    # This is deliberately projection-only: ordinary drawing must not acquire a
    # hidden Paddle/OCR dependency merely because per-page adaptation is enabled.
    _source, canonical, _transform, effective = base._analysis_page(
        image, detector_settings, page_index
    )
    estimate = _projection_layout_estimate(canonical, effective)

    applied: dict[str, int] = {}
    # Resolve every selected scalar except X first.  X registration may use the
    # newly allowed page-specific column count/width/gutter/line scale, while
    # keeping the original Project manual_x as its origin.
    for field, switch in AUTO_LAYOUT_FIELDS:
        if field == "manual_x" or not bool(getattr(current, switch, False)):
            continue
        value = int(getattr(estimate, field))
        setattr(current, field, value)
        applied[field] = value

    if bool(getattr(current, "ordinary_auto_manual_x", False)):
        registration = register_page_manual_x(canonical, current, estimate)
        current.manual_x = int(registration.value)
        applied["manual_x"] = int(registration.value)

    current.manual_columns = False
    return current, estimate, applied


def _column_offsets(settings: AppSettings, count: int) -> list[int]:
    raw = list(getattr(settings, "column_start_offsets", []) or [])
    result: list[int] = []
    for index in range(count):
        try:
            result.append(int(round(float(raw[index]))) if index < len(raw) else 0)
        except (TypeError, ValueError):
            result.append(0)
    return result


def _policy_geometry(
    canonical_width: int,
    settings: AppSettings,
    estimate: LayoutEstimate | None,
) -> tuple[list[int], list[int], list[int]]:
    """Build physical columns from the fields the user actually allowed to vary.

    ``manual_x`` is the one registered page origin.  ``column_width`` and
    ``gutter`` are separate switches, so unselected width/pitch must not leak in
    through ``estimate.column_starts``.  Mild local scan curvature is handled by
    Page Understanding inside each column rather than by giving every column an
    unrelated automatically detected origin.
    """
    _ = estimate  # retained in the signature for compatibility/diagnostics
    count = max(1, min(12, int(getattr(settings, "columns", 1) or 1)))
    width = max(8, int(getattr(settings, "column_width", 700) or 700))
    gutter = max(0, int(getattr(settings, "gutter", 0) or 0))
    manual_x = max(0, int(getattr(settings, "manual_x", 0) or 0))
    offsets = _column_offsets(settings, count)

    starts = [
        manual_x + i * (width + gutter) + offsets[i]
        for i in range(count)
    ]
    widths = [width] * count

    clamped_starts: list[int] = []
    rights: list[int] = []
    for start, item_width in zip(starts, widths):
        left = max(0, min(max(0, canonical_width - 2), int(start)))
        right = max(left + 1, min(canonical_width, left + max(1, int(item_width))))
        clamped_starts.append(left)
        rights.append(right)

    gutters = [gutter if i + 1 < count else 0 for i in range(count)]
    return clamped_starts, rights, gutters


def infer_dictionary_page_layout(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int = 0,
) -> tuple[base.DictionaryPageLayout, AppSettings, dict[str, int]]:
    """Infer one page instance while respecting project fixed/auto field policy."""
    page_settings, estimate, applied = resolve_page_layout_policy(
        image, settings, page_index=page_index
    )
    source, canonical, transform, effective = base._analysis_page(
        image, page_settings, page_index
    )
    page_ink = analysis_ink_mask(
        np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8), effective
    )

    # Top is an explicit policy-controlled field. Bottom intentionally is not:
    # it follows the page/Profile/footer domain, as in the historical ordinary
    # layout contract, rather than becoming another hidden auto-layout switch.
    top = max(0, min(canonical.height - 1, int(getattr(effective, "start_y", 0) or 0)))
    try:
        _observed_top, observed_bottom, _unused_starts, _unused_rights = base._initial_geometry(
            canonical, effective
        )
        bottom = max(top + 1, min(canonical.height, int(observed_bottom)))
    except Exception:
        bottom = canonical.height

    starts, rights, gutters = _policy_geometry(
        canonical.width, page_settings, estimate
    )
    seed = max(8.0, float(getattr(page_settings, "character_height", 26) or 26))

    def column_strips(scale: float) -> tuple[list[np.ndarray], list[list[tuple[int, int]]]]:
        strips: list[np.ndarray] = []
        runs: list[list[tuple[int, int]]] = []
        for left, right in zip(starts, rights):
            column_width = max(1, right - left)
            strip = page_ink[
                top:bottom,
                left:min(canonical.width, left + base._leading_width(column_width, scale)),
            ]
            strips.append(strip)
            runs.append(base._line_runs(strip, scale))
        return strips, runs

    strips, raw_runs = column_strips(seed)
    # ``character_height`` is the fixed/auto *prior*. Actual ink height remains
    # an observed page-instance property, bounded by that prior. This preserves
    # robustness across scan scale/ink spread without silently changing the
    # user's physical column geometry.
    reference = base._normal_height(raw_runs, seed)
    strips, raw_runs = column_strips(reference)

    indent_type = base._indent_type(page_settings)
    columns: list[base.ColumnDesign] = []
    for index, (left, right, gutter_after, strip, runs) in enumerate(
        zip(starts, rights, gutters, strips, raw_runs)
    ):
        column = base.ColumnDesign(index, left, right, gutter_after)
        previous_end = 0
        for y0, y1 in runs:
            line = base._line_feature(index, strip, y0, y1, reference, previous_end)
            previous_end = max(previous_end, y1)
            if line is not None and reference * 0.45 <= line.height <= reference * 1.55:
                column.lines.append(line)
        column.indent_modes = base._indent_modes(column.lines, reference)
        base._assign_indent_semantics(column, indent_type, reference)
        columns.append(column)

    # Preserve the base sparse-lane transfer. The second-stage refinement will
    # still demote continuation/quotation families and choose one entry family.
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
                column.entry_modes.append(base.IndentMode(
                    center=float(np.median([float(line.anchor_x or 0) for line in sparse])),
                    tolerance=reference * 0.32,
                    lines=sparse,
                    shape_consensus=base._shape_consensus(sparse),
                    role="entry",
                ))

    char_width = base._char_width(columns, reference)
    pitch = base._line_pitch(columns, reference)
    display_heads = [
        head
        for column, strip in zip(columns, strips)
        for head in base._display_heads(column, strip, reference, indent_type)
    ]
    display_width = (
        float(np.median([head.width for head in display_heads])) if display_heads else 0.0
    )
    display_height = (
        float(np.median([head.height for head in display_heads])) if display_heads else 0.0
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
    regions = base._regions(
        page_settings,
        page_index,
        source.size,
        transform,
        (body_left, top, body_right, bottom),
    )
    policy = "fixed" if not bool(getattr(settings, "ordinary_auto_layout", False)) else "mixed"
    auto_names = ",".join(sorted(applied)) if applied else "none"
    x_registration = ""
    if estimate is not None and "manual_x" in applied:
        x_registration = (
            f"; x_registration={int(getattr(settings, 'manual_x', 0) or 0)}"
            f"->{int(applied['manual_x'])} raw_projection={int(estimate.manual_x)}"
        )
    reason = (
        f"{len(columns)} columns; body={body_lines}; entry={entry_lines}; "
        f"display={len(display_heads)}; line_h={reference:.1f}; "
        f"char_w={char_width:.1f}; pitch={pitch:.1f}; "
        f"layout_policy={policy}; auto_fields={auto_names}{x_registration}"
    )
    layout = base.DictionaryPageLayout(
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
    return layout, page_settings, applied


def detect_entries_from_page_design(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int = 0,
    page_sections: list[Any] | None = None,
) -> base.LayoutDetectionResult:
    """Policy-aware equivalent of the refined page-design detector."""
    layout, page_settings, applied = infer_dictionary_page_layout(
        image, settings, page_index=page_index
    )
    family = refined.refine_indent_semantics(layout)
    if not layout.reliable:
        return base.LayoutDetectionResult(entries=[], layout=layout)

    entries = base.infer_entry_boundaries(layout, page_sections=page_sections)
    entries.extend(refined._guard_band_entries(
        image,
        page_settings,
        layout,
        family,
        entries,
        page_index=page_index,
    ))
    entries = refined._deduplicate_reading_order(layout, entries)
    if family is None:
        layout.reason += "; refined_entry_family=none"
    else:
        layout.reason += (
            f"; refined_entry_family={family.offset_ratio:.2f}h"
            f" support={family.support} columns={family.column_support}"
            f" shape={family.shape_consensus:.2f}"
        )
    if applied:
        layout.reason += "; policy_applied=" + ",".join(sorted(applied))
    return base.LayoutDetectionResult(entries=entries, layout=layout)


def layout_diagnostics(layout: base.DictionaryPageLayout) -> dict[str, Any]:
    data = refined.layout_diagnostics(layout)
    reason = str(layout.reason or "")
    data["layout_policy"] = {
        "mode": "fixed" if "layout_policy=fixed" in reason else "mixed",
        "principle": (
            "project fields are fixed unless their existing per-page auto switch is enabled; "
            "manual_x is page-wide template registration; indent families remain local page-instance measurements"
        ),
    }
    return data
