from __future__ import annotations

"""Fast physical Layout understanding shared by display and ordinary drawing.

The core resolves physical page geometry and final line roles once, then adds
OCR-independent ordinary evidence from sampled structural symbols and oversized
display heads.  It never runs OCR or semantic parser fusion.  The result is
cached by analysis-image content and settings so 【显示Layout】 and 【普通画线】
reuse exactly the same final role assignment.
"""

from collections import OrderedDict
import hashlib
import weakref
import math
from typing import Any, Iterable

from PIL import Image
from .layout_step_trace import LayoutStepTrace

# Keep the old local name for downstream monkeypatch and cache tests, but
# obtain physical policy/layout through the explicit composition boundary.
from .layout_composition import infer_composed_physical_page_layout as infer_dictionary_page_layout
from .layout_physical_indent import (
    _suppress_display_head_duplicate_entries,
    normalize_layout_roles,
)
from .models import AppSettings, Entry
from .ordinary_evidence_fusion import promote_evidence_to_layout_roles
from .ordinary_large_head_evidence import detect_ordinary_large_head_entries
from .ordinary_symbol_evidence import detect_ordinary_symbol_entries
from .page_understanding import (
    PageUnderstanding,
    _apply_explicit_indent_semantics,
    _generic_body_indent_is_proven,
    _physical_reliable,
    uses_cjk_role_model,
)
from .symbol_evidence import SymbolEvidenceResult


_CACHE_LIMIT = 6
_LAYOUT_CACHE: "OrderedDict[tuple[Any, ...], PageUnderstanding]" = OrderedDict()


_READONLY_IMAGE_DIGESTS: dict[int, tuple[weakref.ReferenceType[Image.Image], Any, tuple[Any, ...]]] = {}
_FINGERPRINT_CHUNK_BYTES = 4 * 1024 * 1024
_FINGERPRINT_STREAM_THRESHOLD = 16 * 1024 * 1024


def _image_fingerprint(image: Image.Image) -> tuple[Any, ...]:
    """Content-accurate hash with bounded temporary memory for large scans.

    Mutable PIL images must *always* rehash: paste/putpixel can modify the same
    ImagingCore in-place. A readonly image instead has copy-on-write semantics
    through public PIL methods, allowing a weak, identity-checked fast path.
    """
    immutable = bool(getattr(image, "readonly", 0))
    if immutable:
        # PIL Image is weakrefable but unhashable; keyed identity + live weakref
        # avoids both WeakKeyDictionary TypeError and recycled-id stale hits.
        hit = _READONLY_IMAGE_DIGESTS.get(id(image))
        if hit is not None and hit[0]() is image and hit[1] is image.im:
            fingerprint = hit[2]
            if fingerprint[:2] == (str(image.mode), tuple(image.size)):
                return fingerprint

    if not immutable:
        previous = _READONLY_IMAGE_DIGESTS.get(id(image))
        if previous is not None and previous[0]() is image:
            # Release an old copy-on-write ImagingCore promptly after mutation.
            _READONLY_IMAGE_DIGESTS.pop(id(image), None)

    digest = hashlib.blake2b(digest_size=16)
    estimated_size = image.width * image.height * max(1, len(image.getbands()))
    if estimated_size < _FINGERPRINT_STREAM_THRESHOLD:
        digest.update(image.tobytes())
    else:
        # The complete tobytes() copy can exceed 100 MB at 600 dpi.
        rows = max(1, _FINGERPRINT_CHUNK_BYTES // max(1, image.width * len(image.getbands())))
        for y in range(0, image.height, rows):
            tile = image.crop((0, y, image.width, min(y + rows, image.height)))
            try:
                digest.update(tile.tobytes())
            finally:
                tile.close()
    result = (str(image.mode), tuple(image.size), digest.digest())
    if immutable:
        key = id(image)

        def on_gc(ref: weakref.ReferenceType[Image.Image]) -> None:
            hit = _READONLY_IMAGE_DIGESTS.get(key)
            if hit is not None and hit[0] is ref:
                _READONLY_IMAGE_DIGESTS.pop(key, None)

        _READONLY_IMAGE_DIGESTS[key] = (weakref.ref(image, on_gc), image.im, result)
    return result


def _settings_fingerprint(settings: AppSettings) -> str:
    # AppSettings is a dataclass-like configuration object. repr() intentionally
    # over-invalidates: changing an unrelated setting may miss the cache, but it
    # can never make stale Layout geometry look valid.
    return repr(settings)


def clear_layout_understanding_cache() -> None:
    _LAYOUT_CACHE.clear()
    _READONLY_IMAGE_DIGESTS.clear()


def _mode_interval(mode: Any) -> tuple[float, float]:
    """Return one physical lane interval in the same normalized-X space."""
    center = float(getattr(mode, "center", 0.0) or 0.0)
    tolerance = max(1.0, float(getattr(mode, "tolerance", 1.0) or 1.0))
    return center - tolerance, center + tolerance


def _body_lane_ids(
    modes: list[Any],
    body: Any,
    reference: float | None,
) -> set[int]:
    """Absorb lanes genuinely adjacent to body in physical-indent space."""
    body_center = float(getattr(body, "center", 0.0) or 0.0)
    body_lo, body_hi = _mode_interval(body)
    ref = max(6.0, float(reference)) if reference is not None else 40.0
    gap_limit = max(4.0, min(12.0, ref * 0.18))
    max_extension = max(14.0, min(28.0, ref * 0.50))

    absorbed: set[int] = {id(body)}
    changed = True
    while changed:
        changed = False
        for mode in modes:
            mode_id = id(mode)
            if mode_id in absorbed:
                continue
            lo, hi = _mode_interval(mode)
            if hi < body_lo:
                gap = body_lo - hi
            elif lo > body_hi:
                gap = lo - body_hi
            else:
                gap = 0.0
            proposed_lo = min(body_lo, lo)
            proposed_hi = max(body_hi, hi)
            if (
                gap <= gap_limit
                and proposed_lo >= body_center - max_extension
                and proposed_hi <= body_center + max_extension
            ):
                absorbed.add(mode_id)
                body_lo, body_hi = proposed_lo, proposed_hi
                changed = True
    return absorbed


def _resolve_directional_body_lanes(layout: Any) -> None:
    """Choose the body family from explicit indent polarity, not row counts."""
    indent_type = str(getattr(layout, "indent_type", "body") or "body")
    if indent_type == "none":
        # No-indent pages deliberately leave directional indentation out of the
        # entry decision.  Visual-symbol and large-head evidence can still
        # promote rows later in this module.
        for column in list(getattr(layout, "columns", []) or []):
            for line in list(getattr(column, "lines", []) or []):
                line.role = "body"
            for mode in list(getattr(column, "indent_modes", []) or []):
                mode.role = "body"
            column.entry_modes = []
        return

    reference = float(getattr(layout, "ordinary_line_height", 0.0) or 0.0)
    reference_arg = reference if reference > 0 else None

    for column in list(getattr(layout, "columns", []) or []):
        modes = list(getattr(column, "indent_modes", []) or [])
        if not modes:
            continue

        supports = [int(getattr(mode, "support", 0) or 0) for mode in modes]
        max_support = max(supports, default=0)
        if max_support <= 0:
            continue

        stable_threshold = max(2, int(math.ceil(float(max_support) * 0.25)))
        stable_modes = [
            mode
            for mode in modes
            if int(getattr(mode, "support", 0) or 0) >= stable_threshold
        ]
        if not stable_modes:
            stable_modes = [max(modes, key=lambda mode: int(getattr(mode, "support", 0) or 0))]

        if indent_type == "headword" and len(layout.columns) >= 2:
            # An outside-column band can be a gutter/neighbor projection
            # artifact, not the actual text-body origin. If chosen as the
            # leftmost body anchor, it promotes every normal body row between
            # that artifact and the genuinely indented headword band.
            #
            # Only discard such a band from BODY-SEED selection when two
            # independently supported, well-separated in-column families
            # remain, and one is substantially stronger than the outside
            # band. Otherwise preserve the original directional semantics.
            # Never remove physical lines, invent bracket evidence, or change
            # the Entry/PDIC representation.
            outside_limit = -max(24.0, reference * 0.70)
            inside = [
                mode for mode in stable_modes
                if float(getattr(mode, "center", 0.0) or 0.0) >= outside_limit
            ]
            outside = [
                mode for mode in stable_modes
                if float(getattr(mode, "center", 0.0) or 0.0) < outside_limit
            ]
            if len(inside) >= 2 and outside:
                centers = [
                    float(getattr(mode, "center", 0.0) or 0.0)
                    for mode in inside
                ]
                strongest_inside = max(
                    int(getattr(mode, "support", 0) or 0) for mode in inside
                )
                strongest_outside = max(
                    int(getattr(mode, "support", 0) or 0) for mode in outside
                )
                if (
                    max(centers) - min(centers) >= max(20.0, reference * 0.65)
                    and strongest_inside >= 1.5 * strongest_outside
                ):
                    stable_modes = inside

        if indent_type == "body":
            desired_body = max(
                stable_modes,
                key=lambda mode: float(getattr(mode, "center", 0.0) or 0.0),
            )
        else:
            desired_body = min(
                stable_modes,
                key=lambda mode: float(getattr(mode, "center", 0.0) or 0.0),
            )

        body_ids = _body_lane_ids(modes, desired_body, reference_arg)
        body_centers = [
            float(getattr(mode, "center", 0.0) or 0.0)
            for mode in modes
            if id(mode) in body_ids
        ]
        body_min = min(body_centers)
        body_max = max(body_centers)

        for line in list(getattr(column, "lines", []) or []):
            line.role = "body"
        for mode in modes:
            mode.role = "body"

        if indent_type == "headword":
            entry_modes = [
                mode
                for mode in modes
                if id(mode) not in body_ids
                and float(getattr(mode, "center", 0.0) or 0.0) > body_max
            ]
        else:
            entry_modes = [
                mode
                for mode in modes
                if id(mode) not in body_ids
                and float(getattr(mode, "center", 0.0) or 0.0) < body_min
            ]

        for mode in entry_modes:
            mode.role = "entry"
            for line in list(getattr(mode, "lines", []) or []):
                line.role = "entry"

        column.body_mode = desired_body
        column.entry_modes = list(entry_modes)

    _suppress_display_head_duplicate_entries(layout)


def _suppress_large_evidence_duplicate_entries(
    layout: Any,
    large_entries: Iterable[Entry],
) -> int:
    """Keep one Layout entry row inside each detected oversized head extent.

    The historical duplicate suppressor consumes ``layout.display_heads``.  The
    universal ordinary large-head detector is newer and can positively detect an
    oversized glyph even when that older list is absent or vertically too short.
    Its evidence already carries the observed glyph height, so use that same
    physical evidence to collapse every logical row start that falls *inside*
    the glyph.  The first/top entry boundary is retained; later rows are body.

    This only demotes duplicate rows within a positively detected oversized-head
    box.  It does not widen generic Y de-duplication and cannot merge unrelated
    ordinary entries outside that observed glyph extent.
    """
    columns = list(getattr(layout, "columns", []) or [])
    if not columns:
        return 0

    source_size = tuple(getattr(layout, "source_size", (0, 0)) or (0, 0))
    body_top = int(getattr(layout, "body_top", 0) or 0)
    reference = max(4.0, float(getattr(layout, "ordinary_line_height", 1.0) or 1.0))
    removed = 0

    for evidence in list(large_entries):
        try:
            observed_height = float(getattr(evidence, "ocr_visual_run_height", 0.0) or 0.0)
            if observed_height < reference * 1.20:
                continue
            canonical_x, canonical_y = layout.transform.source_to_canonical_point(
                int(evidence.x),
                int(evidence.y),
                source_size,
            )
            canonical_x = float(canonical_x)
            top = float(canonical_y) - float(body_top)
        except (AttributeError, TypeError, ValueError):
            continue

        # Evidence is emitted at column.left.  Prefer the containing column and
        # otherwise use the nearest left edge so tiny transform rounding cannot
        # make us miss the correct column.
        containing = [
            column
            for column in columns
            if float(getattr(column, "left", 0) or 0) - 1.0
            <= canonical_x
            <= float(getattr(column, "right", 0) or 0) + 1.0
        ]
        column = min(
            containing or columns,
            key=lambda item: abs(float(getattr(item, "left", 0) or 0) - canonical_x),
        )

        bottom = top + observed_height
        top_tolerance = min(reference * 0.35, max(3.0, observed_height * 0.12))
        overlapping = [
            line
            for line in list(getattr(column, "lines", []) or [])
            if str(getattr(line, "role", "body") or "body") == "entry"
            and float(getattr(line, "y0", 0) or 0) >= top - top_tolerance
            and float(getattr(line, "y0", 0) or 0) < bottom
        ]
        if len(overlapping) <= 1:
            continue

        # Keep the boundary that best represents the physical top of the glyph;
        # this is also the row to which large-head evidence was promoted.
        keeper = min(
            overlapping,
            key=lambda line: (
                abs(float(getattr(line, "y0", 0) or 0) - top),
                float(getattr(line, "y0", 0) or 0),
            ),
        )
        for line in overlapping:
            if line is keeper:
                continue
            line.role = "body"
            removed += 1

    return removed


def _debug_layout_role_snapshot(layout: Any) -> dict[int, dict[str, Any]]:
    """Role and provenance of each physical row; diagnostics only."""
    from .entry_classification import get_layout_line_classification

    snapshot: dict[int, dict[str, Any]] = {}
    for index, column in enumerate(list(getattr(layout, "columns", ()) or ())):
        for line in list(getattr(column, "lines", ()) or ()):
            snapshot[id(line)] = {
                "column": index,
                "canonical_y": int(layout.body_top) + int(line.y0),
                "role": str(getattr(line, "role", "") or ""),
                "source": str(get_layout_line_classification(line).entry_source),
            }
    return snapshot


def _debug_role_changes(
    previous: dict[int, dict[str, Any]],
    current: dict[int, dict[str, Any]],
    stage: str,
) -> list[dict[str, Any]]:
    changes = []
    for row_id, after in current.items():
        before = previous.get(row_id)
        if before is None:
            changes.append({"stage": stage, "before": None, "after": after})
        elif (
            before["role"] != after["role"]
            or before["source"] != after["source"]
        ):
            changes.append({
                "stage": stage,
                "before": before,
                "after": after,
            })
    return changes


def _apply_universal_ordinary_evidence(
    image: Image.Image,
    understanding: PageUnderstanding,
    settings: AppSettings,
    *,
    large_head_diagnostics: list[dict[str, Any]] | None = None,
    large_head_debug_context: dict[str, Any] | None = None,
    trace: LayoutStepTrace | None = None,
) -> tuple[int, int]:
    """OR-promote sampled-symbol and oversized-head evidence onto Layout rows."""
    symbol_entries = detect_ordinary_symbol_entries(image, understanding, settings)
    large_entries = detect_ordinary_large_head_entries(
        image, understanding, settings, diagnostics=large_head_diagnostics,
    )
    prior = (
        _debug_layout_role_snapshot(understanding.layout)
        if large_head_debug_context is not None else None
    )
    symbol_promoted = promote_evidence_to_layout_roles(understanding, symbol_entries)
    if trace is not None:
        trace.add_layout("symbol_evidence", "符号证据融合",
                         "由括号、特殊视觉符号提出词头证据，并观察角色变化。",
                         understanding.layout,
                         details={"candidates": len(symbol_entries),
                                  "promoted": int(symbol_promoted)},
                         candidates=[{
                             "status": "symbol", "source_anchor": [
                                 int(entry.x), int(entry.y),
                             ],
                             "word": str(getattr(entry, "word", "") or ""),
                         } for entry in symbol_entries])
    after_symbol = (
        _debug_layout_role_snapshot(understanding.layout)
        if prior is not None else None
    )
    large_promoted = promote_evidence_to_layout_roles(understanding, large_entries)
    if trace is not None:
        trace.add_layout("large_head_evidence", "大字头证据融合",
                         "实际大字头检测结果参与行角色调整；未达到条件的候选不会自动提升。",
                         understanding.layout,
                         details={"candidates": len(large_entries),
                                  "promoted": int(large_promoted)},
                         candidates=[{
                             "status": str(item.get("status", "unknown")),
                             "source_box": list(item.get("source_box", ())),
                             "height_ratio": float(item.get("height_ratio", 0) or 0),
                             "detector_output": bool(item.get("detector_output", False)),
                         } for item in (large_head_diagnostics or ())])
    after_large = (
        _debug_layout_role_snapshot(understanding.layout)
        if prior is not None else None
    )
    # First retain the historical display-head safeguard, then consume the
    # current large-head evidence itself.  The latter closes the gap where the
    # newer detector sees a 2-3-row display glyph but layout.display_heads does
    # not cover its full vertical extent.
    _suppress_display_head_duplicate_entries(understanding.layout)
    _suppress_large_evidence_duplicate_entries(understanding.layout, large_entries)
    if trace is not None:
        trace.add_layout("duplicate_suppression", "大字碎片去重",
                         "防止大字内部的碎片行变成重复词条起点。", understanding.layout)
    if large_head_debug_context is not None:
        final = _debug_layout_role_snapshot(understanding.layout)
        large_head_debug_context["role_transitions"] = (
            _debug_role_changes(prior or {}, after_symbol or {}, "symbol_evidence")
            + _debug_role_changes(after_symbol or {}, after_large or {}, "large_head_fusion")
            + _debug_role_changes(after_large or {}, final, "large_head_dedup")
        )
        large_head_debug_context["promotion_counts"] = {
            "symbol_promoted": int(symbol_promoted),
            "large_head_promoted": int(large_promoted),
        }
        large_head_debug_context["role_counts"] = {
            stage: {
                role: sum(row["role"] == role for row in snapshot.values())
                for role in ("entry", "body", "unknown")
            }
            for stage, snapshot in (
                ("before_symbol", prior or {}),
                ("after_symbol", after_symbol or {}),
                ("after_large", after_large or {}),
                ("after_dedup", final),
            )
        }
    return symbol_promoted, large_promoted


def _publish_captured_result(
    result: PageUnderstanding,
    page_index: int,
) -> PageUnderstanding:
    """Publish LayoutRows for the current explicit capture scope, if any."""
    from .layout_rows_cache import publish_captured_layout

    publish_captured_layout(result.layout, int(page_index))
    return result


def understand_layout_core(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int = 0,
    large_head_diagnostics: list[dict[str, Any]] | None = None,
    large_head_debug_context: dict[str, Any] | None = None,
    trace: LayoutStepTrace | None = None,
) -> PageUnderstanding:
    """Return Layout roles, optionally tracing the *production* detector stage.

    Debug traces bypass shared Layout caching and capture publication. An
    isolated diagnostic run never mutates the normal cached Layout objects.
    """
    from time import perf_counter as _perf
    from .quality.draw_performance_profile import enabled as _prof_on, record_page
    _profiling = _prof_on()
    _last = _perf() if _profiling else 0.0
    _stages = {}
    def _mark(name):
        nonlocal _last
        if _profiling:
            now = _perf()
            _stages[name] = now - _last
            _last = now
    def _finish(cache_status):
        if _profiling:
            _mark("layout_core_finalization")
            record_page("<substage>", page_index, _stages,
                        stage_group=f"layout_core_{cache_status}")
    # Diagnostic replay records a separate production pass, never publishes
    # LayoutRows and never mutates/reuses the shared normal result cache.
    key = None
    if trace is None and large_head_diagnostics is None and large_head_debug_context is None:
        key = (
            _image_fingerprint(image),
            _settings_fingerprint(settings),
            int(page_index),
        )
        cached = _LAYOUT_CACHE.get(key)
        if cached is not None:
            _LAYOUT_CACHE.move_to_end(key)
            _mark("layout_core_cache_lookup")
            result = _publish_captured_result(cached, page_index)
            _finish("cache_hit")
            return result

    _mark("layout_core_cache_lookup")
    layout, page_settings, applied = infer_dictionary_page_layout(
        image, settings, page_index=int(page_index),
        **({"trace": trace} if trace is not None else {}),
    )
    _mark("layout_core_layout_inference")
    _apply_explicit_indent_semantics(layout, page_settings)
    # Even when the user explicitly chose no indentation, the low-level
    # physical detector has to be neutralized once. This is state
    # normalization, *not* an inferred entry/body decision, and must happen
    # before the next evidence family examines the physical rows.
    normalize_layout_roles(layout)
    if layout.indent_type != "none":
        if trace is not None:
            trace.add_layout("indent_semantics", "缩进语义判定",
                             "应用 Project/Profile 缩进语义并重新归一化行角色。", layout,
                             details={"indent_type": str(layout.indent_type)})
        _resolve_directional_body_lanes(layout)
        if trace is not None:
            trace.add_layout("body_lanes", "正文缩进族调整",
                             "调整正文缩进带对词条行与正文行的判定。", layout)
    # For 'none', normalize_layout_roles has already set every provisional
    # physical line and lane to body and cleared entry_modes. The no-indent
    # arm of _resolve_directional_body_lanes would repeat exactly that reset.
    # Bypass the redundant operation as well as its misleading replay stages.
    if trace is not None and layout.indent_type == "none":
        # Internal role neutralization is not a visual-evidence change.
        # Update the diff baseline without emitting another step.
        trace.adopt_unshown_role_baseline(layout)
    if layout.indent_type == "none":
        # Both consumers below guard on indent_type == 'body' and return only
        # zeros for no-indent. Their names would misleadingly suggest an
        # analysis took place. Skip the actual no-op calls and their replay
        # frames; the next real operation is symbol/large-head evidence.
        visual_role_check = {
            "checked_columns": 0, "repaired_columns": 0,
            "demoted_rows": 0, "repaired_indices": [],
        }
        restored_indents = {
            "rescued_columns": 0, "rescued_rows": 0, "cjk_bracket_rows": 0,
        }
    else:
        from .layout_role_visual_consistency import suppress_contradictory_cjk_body_lane_entries
        visual_role_check = suppress_contradictory_cjk_body_lane_entries(
            image, page_settings, layout,
        )
        if trace is not None:
            trace.add_layout(
                "visual_consistency", "视觉一致性复核",
                "检查可见墨迹与缩进带的冲突，撤销无独立证据的错误词头。",
                layout, details={
                    "indent_type": str(layout.indent_type),
                    "demoted_rows": int(visual_role_check["demoted_rows"]),
                    "repaired_columns": int(visual_role_check["repaired_columns"]),
                },
            )
        # Keep visible Layout and downstream ordinary drawings consistent:
        # restore only when a separate observation proves actual entry starts.
        from .layout_column_indent_recovery import restore_proven_column_indents
        restored_indents = restore_proven_column_indents(
            image, page_settings, layout, page_index=int(page_index),
        )
        if trace is not None:
            trace.add_layout("indent_recovery", "缺失缩进恢复",
                             "只有独立的字形/几何证据充分时才恢复未识别的词头起点。",
                             layout, details={
                                 "rescued_columns": int(restored_indents["rescued_columns"]),
                                 "rescued_rows": int(restored_indents["rescued_rows"]),
                             })

    _mark("layout_core_role_normalize_recovery")
    physical = _physical_reliable(layout)
    cjk = uses_cjk_role_model(page_settings)
    generic_body = bool(
        not cjk
        and physical
        and _generic_body_indent_is_proven(layout)
    )
    role_model = "cjk" if cjk else "generic"

    result = PageUnderstanding(
        layout=layout,
        page_settings=page_settings,
        applied_layout_fields=dict(applied),
        role_model=role_model,
        physical_reliable=physical,
        semantic_reliable=False,
        semantic_entries=[],
        generic_body_indent_reliable=generic_body,
        family_offset_ratio=None,
        symbol_evidence=SymbolEvidenceResult(markers=[]),
    )

    _mark("layout_core_role_metadata")
    symbol_promoted, large_promoted = _apply_universal_ordinary_evidence(
        image,
        result,
        page_settings,
        large_head_diagnostics=large_head_diagnostics,
        large_head_debug_context=large_head_debug_context,
        trace=trace,
    )
    _mark("layout_core_symbol_large_head_evidence")
    from .layout_verified_oversized_heads import recover_verified_oversized_heads
    verified_heads = (
        recover_verified_oversized_heads(
            image, layout, visual_role_check["repaired_indices"],
        )
        if bool(getattr(page_settings, "profile_cjk_allow_single_headword", True))
        else {"verified_glyphs": 0, "promoted_heads": 0, "demoted_fragments": 0}
    )
    if trace is not None:
        trace.add_layout("verified_oversized", "大字头最终复核",
                         "再次核实大字形与物理行对应关系；移除无效的大字碎片。",
                         layout, details=dict(verified_heads))
    _mark("layout_core_verified_oversized")
    # Final conservative check for a split large glyph. An indent-derived
    # second start is removed only if the leading ink physically continues
    # across that boundary; independent symbol/head evidence is preserved.
    from .layout_oversized_ink_continuation import suppress_oversized_ink_continuation
    ink_continuation = (
        suppress_oversized_ink_continuation(image, layout)
        if cjk else {"candidate_pairs": 0, "demoted_fragments": 0}
    )
    if trace is not None:
        trace.add_layout(
            "oversized_ink_continuation", "大字头内部连续墨迹复核",
            "只撤销与上方字形连续、且无独立证据的词头重复起点。",
            layout, details=dict(ink_continuation),
        )
    _mark("layout_core_oversized_ink_continuation")
    # Keep a separate immutable record of why each final Layout role became an
    # entry. Future confidence gates must be validated against real scans
    # before changing this canonical ordinary-mode output.
    from .geometry.boundary_evidence import proposed_layout_boundaries, serialize_proposals
    result.boundary_proposals = serialize_proposals(proposed_layout_boundaries(result))
    layout.reason += (
        f"; page_understanding={role_model}:layout_core"
        f" physical_reliable={int(physical)}"
        f" semantic_reliable=0"
        f" generic_body_indent={int(generic_body)}"
        f" indent_semantics={layout.indent_type}"
        f" ordinary_symbol_promoted={int(symbol_promoted)}"
        f" ordinary_large_head_promoted={int(large_promoted)}"
        f" recovered_indent_columns={int(restored_indents['rescued_columns'])}"
        f" recovered_indent_rows={int(restored_indents['rescued_rows'])}"
        f" visual_body_lane_repaired={int(visual_role_check['repaired_columns'])}"
        f" visual_body_lane_demoted={int(visual_role_check['demoted_rows'])}"
        f" verified_oversized_glyphs={int(verified_heads['verified_glyphs'])}"
        f" verified_oversized_promoted={int(verified_heads['promoted_heads'])}"
        f" verified_oversized_demoted={int(verified_heads['demoted_fragments'])}"
        f" large_ink_continuation_demoted={int(ink_continuation['demoted_fragments'])}"
    )

    if trace is not None:
        trace.add_layout("final", "最终 Layout 结果",
                         "本次真实 Layout Core 最终采用的列与行角色；之后的普通画线仍可能有单独的过滤阶段。",
                         layout, details={
                             "boundary_proposals": len(result.boundary_proposals),
                             "physical_reliable": bool(physical),
                             "role_model": role_model,
                         })
        _finish("trace")
        return result
    if large_head_diagnostics is not None or large_head_debug_context is not None:
        _finish("diagnostic")
        return result
    _LAYOUT_CACHE[key] = result
    _LAYOUT_CACHE.move_to_end(key)
    while len(_LAYOUT_CACHE) > _CACHE_LIMIT:
        _LAYOUT_CACHE.popitem(last=False)
    published = _publish_captured_result(result, page_index)
    _finish("cache_miss")
    return published
