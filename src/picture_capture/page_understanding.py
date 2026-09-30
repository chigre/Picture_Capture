from __future__ import annotations

"""Shared OCR-independent page understanding for every drawing mode.

This module sits *above* detector-specific candidate generation.  It describes
facts about the printed/scanned dictionary page once, then exposes those facts
to ordinary drawing, OCR drawing and combined drawing.

The separation is deliberate:

* physical page understanding is language-agnostic (body, columns, ordinary
  scale, actual text rows and indentation distribution);
* entry-role semantics are profile/layout-family specific;
* detector observations (VB separators or OCR candidates) remain independent
  evidence and are arbitrated against page understanding later.

For CJK pages we reuse the validated refined entry-family/display-head model and
therefore obtain authoritative layout-derived boundaries.  For non-CJK pages we
currently keep semantic generation conservative: the physical model is shared,
but it is used primarily as layout evidence/negative evidence.  In particular,
when the user explicitly selects ``正文缩进``, a stable inward body lane can veto
candidate rows that are demonstrably body paragraphs without inventing new
Latin headwords.
"""

from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from . import dictionary_page_design as base
from . import dictionary_page_design_refined as refined
from .boundary_placement import refine_boundaries_toward_head_top
from .dictionary_page_layout_policy import infer_dictionary_page_layout
from .models import AppSettings, Entry


@dataclass(slots=True)
class BlockLayoutEvidence:
    """Nearest designed text-block evidence for one detector candidate."""

    column_index: int
    role: str
    boundary_y: int
    boundary_distance: float
    anchor_offset_ratio: float | None
    body_distance_ratio: float | None
    on_body_lane: bool
    in_entry_direction: bool


@dataclass(slots=True)
class PageUnderstanding:
    """One reusable page-analysis result shared by all entry detectors."""

    layout: base.DictionaryPageLayout
    page_settings: AppSettings
    applied_layout_fields: dict[str, int]
    role_model: str
    physical_reliable: bool
    semantic_reliable: bool
    semantic_entries: list[Entry] = field(default_factory=list)
    generic_body_indent_reliable: bool = False
    family_offset_ratio: float | None = None
    arbitration_stats: dict[str, int] = field(default_factory=dict)

    @property
    def line_height(self) -> float:
        return max(1.0, float(self.layout.ordinary_line_height))


def uses_cjk_role_model(settings: AppSettings) -> bool:
    """Return whether the validated CJK entry-role model is appropriate."""
    profile_id = str(getattr(settings, "dictionary_profile_id", "") or "").lower()
    ocr_language = str(getattr(settings, "ocr_language", "") or "").lower()
    paddle_language = str(getattr(settings, "paddle_language", "") or "").lower()
    writing = str(getattr(settings, "layout_writing_mode", "horizontal-tb") or "horizontal-tb")
    if writing.startswith("vertical"):
        return False
    return bool(
        "cjk" in profile_id
        or any(token in ocr_language for token in (
            "chi_sim", "chi_tra", "chinese", "han", "jpn", "jpn_vert",
        ))
        or paddle_language in {"ch", "chi_sim", "chi_tra", "chinese_cht", "japan"}
    )


def _physical_reliable(layout: base.DictionaryPageLayout) -> bool:
    if not layout.columns:
        return False
    line_count = sum(len(column.lines) for column in layout.columns)
    populated = sum(bool(column.lines) for column in layout.columns)
    return bool(
        populated >= max(1, len(layout.columns) - 1)
        and line_count >= max(5, 3 * len(layout.columns))
        and layout.ordinary_line_height >= 4.0
    )


def _generic_body_indent_is_proven(layout: base.DictionaryPageLayout) -> bool:
    """Conservatively prove a distinct inward body lane on non-CJK pages.

    This is intentionally only a *negative-evidence* gate.  It never generates
    Latin entries.  The explicit user choice ``正文缩进`` supplies the polarity;
    the page still has to show a stable body lane plus a separate outer lane.
    """
    if layout.indent_type != "body" or not layout.columns:
        return False
    reference = max(1.0, float(layout.ordinary_line_height))
    body_support = 0
    outer_support = 0
    contrasted_columns = 0
    for column in layout.columns:
        body = column.body_mode
        if body is None or body.support < 3:
            continue
        body_support += body.support
        outer = [
            mode for mode in column.indent_modes
            if mode is not body
            and float(body.center) - float(mode.center) >= reference * 0.30
            and mode.support >= 2
        ]
        if outer:
            contrasted_columns += 1
            outer_support += sum(mode.support for mode in outer)
    return bool(
        body_support >= max(5, 2 * len(layout.columns))
        and outer_support >= 2
        and contrasted_columns >= 1
    )


def _clear_generic_entry_roles(layout: base.DictionaryPageLayout) -> None:
    """Keep physical indent modes while refusing CJK-specific semantics."""
    for column in layout.columns:
        for mode in column.indent_modes:
            mode.role = "body" if mode is column.body_mode else "other_indent"
        column.entry_modes = []
        body_ids = {
            id(line) for line in (column.body_mode.lines if column.body_mode is not None else [])
        }
        for line in column.lines:
            line.role = "body" if id(line) in body_ids else "other_indent"


def understand_page(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int = 0,
    page_sections: list[Any] | None = None,
) -> PageUnderstanding:
    """Recover one page once for ordinary/OCR/combined drawing.

    No OCR engine is called here.  The existing fixed/per-page-auto layout policy
    remains authoritative for physical fields.
    """
    layout, page_settings, applied = infer_dictionary_page_layout(
        image, settings, page_index=page_index,
    )
    physical = _physical_reliable(layout)
    cjk = uses_cjk_role_model(page_settings)
    semantic_entries: list[Entry] = []
    semantic_reliable = False
    family_ratio: float | None = None
    role_model = "cjk" if cjk else "generic"

    if cjk:
        family = refined.refine_indent_semantics(layout)
        if family is not None:
            family_ratio = float(family.offset_ratio)
        if layout.reliable:
            semantic_entries = base.infer_entry_boundaries(
                layout, page_sections=page_sections,
            )
            semantic_entries.extend(refined._guard_band_entries(
                image,
                page_settings,
                layout,
                family,
                semantic_entries,
                page_index=page_index,
            ))
            semantic_entries = refined._deduplicate_reading_order(
                layout, semantic_entries,
            )
            semantic_entries = refine_boundaries_toward_head_top(
                image,
                page_settings,
                layout,
                semantic_entries,
                page_index=page_index,
            )
        semantic_reliable = bool(
            physical
            and layout.reliable
            and (semantic_entries or family is not None or layout.display_heads)
        )
    else:
        # The physical model is shared, but do not reinterpret Latin/non-CJK
        # indent modes with the CJK structural-family selector.
        _clear_generic_entry_roles(layout)

    generic_body = bool(
        not cjk
        and physical
        and _generic_body_indent_is_proven(layout)
    )
    layout.reason += (
        f"; page_understanding={role_model}"
        f" physical_reliable={int(physical)}"
        f" semantic_reliable={int(semantic_reliable)}"
        f" generic_body_indent={int(generic_body)}"
    )
    return PageUnderstanding(
        layout=layout,
        page_settings=page_settings,
        applied_layout_fields=dict(applied),
        role_model=role_model,
        physical_reliable=physical,
        semantic_reliable=semantic_reliable,
        semantic_entries=list(semantic_entries),
        generic_body_indent_reliable=generic_body,
        family_offset_ratio=family_ratio,
    )


def _column_for_source_point(
    understanding: PageUnderstanding,
    x: int,
    y: int,
) -> tuple[int, int, int] | None:
    layout = understanding.layout
    if not layout.columns:
        return None
    u, v = layout.transform.source_to_canonical_point(
        int(x), int(y), layout.source_size,
    )
    inside = [
        column for column in layout.columns
        if int(column.left) - understanding.line_height <= u <= int(column.right) + understanding.line_height
    ]
    if inside:
        column = min(
            inside,
            key=lambda item: abs(u - int(item.left)),
        )
    else:
        column = min(
            layout.columns,
            key=lambda item: abs(u - int(item.left)),
        )
    return int(column.index), int(u), int(v)


def block_evidence_for_entry(
    understanding: PageUnderstanding,
    entry: Entry,
) -> BlockLayoutEvidence | None:
    """Return the designed block immediately associated with a marker Y."""
    if not understanding.physical_reliable:
        return None
    located = _column_for_source_point(
        understanding, int(entry.x), int(entry.y),
    )
    if located is None:
        return None
    column_index, _u, v = located
    layout = understanding.layout
    if not (0 <= column_index < len(layout.columns)):
        return None
    column = layout.columns[column_index]
    if not column.lines:
        return None

    reference = understanding.line_height
    local_v = float(v - int(layout.body_top))
    candidates: list[tuple[float, base.LayoutLine, int]] = []
    for line in column.lines:
        boundary_local = int(base._boundary_before(
            column.lines, int(line.y0), reference,
        ))
        candidates.append((abs(local_v - boundary_local), line, boundary_local))
    distance, line, boundary_local = min(candidates, key=lambda item: item[0])

    body = column.body_mode
    anchor_offset_ratio: float | None = None
    body_distance_ratio: float | None = None
    on_body_lane = False
    in_entry_direction = False
    if body is not None and line.anchor_x is not None:
        raw_offset = float(line.anchor_x) - float(body.center)
        anchor_offset_ratio = raw_offset / reference
        body_distance_ratio = abs(raw_offset) / reference
        body_tolerance = max(0.20, float(body.tolerance) / reference)
        on_body_lane = body_distance_ratio <= body_tolerance
        sign = 1.0 if layout.indent_type == "headword" else -1.0
        in_entry_direction = sign * anchor_offset_ratio >= 0.30

    _bx, boundary_source_y = layout.transform.canonical_to_source_point(
        int(column.left),
        int(layout.body_top) + int(boundary_local),
        layout.source_size,
    )
    return BlockLayoutEvidence(
        column_index=column_index,
        role=str(line.role or "unknown"),
        boundary_y=int(boundary_source_y),
        boundary_distance=float(distance),
        anchor_offset_ratio=anchor_offset_ratio,
        body_distance_ratio=body_distance_ratio,
        on_body_lane=bool(on_body_lane),
        in_entry_direction=bool(in_entry_direction),
    )


def page_understanding_diagnostics(
    understanding: PageUnderstanding,
) -> dict[str, Any]:
    """Serialize the shared layer for training-package/debug analysis."""
    from .dictionary_page_design import layout_diagnostics

    return {
        "role_model": understanding.role_model,
        "physical_reliable": bool(understanding.physical_reliable),
        "semantic_reliable": bool(understanding.semantic_reliable),
        "generic_body_indent_reliable": bool(
            understanding.generic_body_indent_reliable
        ),
        "semantic_entry_count": len(understanding.semantic_entries),
        "entry_family_offset_ratio": understanding.family_offset_ratio,
        "auto_layout_fields": dict(understanding.applied_layout_fields),
        "arbitration_stats": dict(understanding.arbitration_stats),
        "layout": layout_diagnostics(understanding.layout),
    }
