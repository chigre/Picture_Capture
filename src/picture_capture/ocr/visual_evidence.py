"""Image-first OCR visual symbol, marker, and CJK projection evidence.

One canonical owner for component extraction, configured visual symbol and
trusted lane detection, matching visual markers to OCR lines, and CJK
projection/right-context and oversized-glyph word recovery.

All historical OCR callable and symbol-policy dependencies are captured from
the existing core at call time. The canonical owner imports neither that core
nor GUI/native OCR engines.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING
import math
import re
import unicodedata

import numpy as np
from PIL import Image, ImageOps

from ..models import AppSettings
from .headword_models import OCRLine, OCRRecord, HeadwordParse
from ..profile.dictionary import DictionaryProfile

if TYPE_CHECKING:
    from ..processing import Geometry


@dataclass(frozen=True)
class VisualEvidenceDeps:
    """Per-invocation immutable mapping of original OCR visual operations."""
    _binary_rle_components: object
    _visual_marker_shape_metrics: object
    _visual_family_symbol: object
    _classify_visual_symbol_component: object
    _trusted_visual_marker_lanes: object
    _apply_trusted_visual_marker_lanes: object
    _detect_visual_entry_markers: object
    _match_visual_entry_markers_to_lines: object
    _parse_cjk_visual_marker_line: object
    _parse_visual_configured_symbol_line: object
    _leading_cjk_ideograph: object
    _cjk_visual_projection_runs: object
    _cjk_right_context_metrics: object
    _cjk_right_context_features: object
    _cjk_candidate_right_context_metrics: object
    _cjk_candidate_right_context_features: object
    _cjk_word_for_visual_run: object
    _otsu_threshold: object
    _is_chinese_ocr: object
    _repair_headword_ocr: object
    _parse_chinese_bracketed_headword: object
    _is_japanese_ocr: object
    _is_single_cjk_ideograph: object
    _true_runs: object
    parse_headword_text: object
    _parse_cjk_single_with_pinyin: object
    match_visual_marker_template: object
    _SYMBOL_FAMILY_BY_LITERAL: object
    _BRACKET_CLOSER_BY_OPENER: object


def _binary_rle_components(
    deps: VisualEvidenceDeps, 
    mask: np.ndarray,
) -> list[tuple[int, int, int, int, int]]:
    """Dependency-free 8-connected components for visual marker analysis."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2 or mask.size == 0:
        return []
    height, _width = mask.shape
    parent: list[int] = []
    rank: list[int] = []
    boxes: list[list[int]] = []

    def make(x0: int, x1: int, y: int) -> int:
        index = len(parent)
        parent.append(index)
        rank.append(0)
        boxes.append([x0, y, x1, y + 1, x1 - x0])
        return index

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1

    previous: list[tuple[int, int, int]] = []
    for y in range(height):
        padded = np.r_[False, mask[y], False].astype(np.int8)
        changes = np.diff(padded)
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1)
        current: list[tuple[int, int, int]] = []
        cursor = 0
        for x0, x1 in zip(starts.tolist(), ends.tolist()):
            component = make(x0, x1, y)
            while cursor < len(previous) and previous[cursor][1] < x0 - 1:
                cursor += 1
            k = cursor
            while k < len(previous) and previous[k][0] <= x1 + 1:
                px0, px1, prior = previous[k]
                if px1 >= x0 - 1:
                    union(component, prior)
                k += 1
            current.append((x0, x1, component))
        previous = current

    merged: dict[int, list[int]] = {}
    for index, box in enumerate(boxes):
        root = find(index)
        target = merged.setdefault(root, [box[0], box[1], box[2], box[3], 0])
        target[0] = min(target[0], box[0])
        target[1] = min(target[1], box[1])
        target[2] = max(target[2], box[2])
        target[3] = max(target[3], box[3])
        target[4] += box[4]
    return [tuple(value) for value in merged.values()]


def _visual_marker_shape_metrics(
    deps: VisualEvidenceDeps, mask: np.ndarray) -> dict[str, float]:
    """Geometry descriptors shared by configured visual symbol families."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2 or mask.size == 0 or not mask.any():
        return {
            "density": 0.0, "central_ink": 1.0, "outer_ink_fraction": 1.0,
            "top_ink": 0.0, "bottom_ink": 0.0, "left_ink": 0.0, "right_ink": 0.0,
            "corner_ink": 0.0, "midrow_width": 0.0, "toprow_width": 0.0,
            "bottomrow_width": 0.0,
        }
    height, width = mask.shape
    density = float(mask.mean())
    y0, y1 = round(height * 0.30), round(height * 0.70)
    x0, x1 = round(width * 0.30), round(width * 0.70)
    central = mask[max(0, y0):max(y0 + 1, y1), max(0, x0):max(x0 + 1, x1)]
    central_ink = float(central.mean()) if central.size else 1.0

    yy, xx = np.indices(mask.shape, dtype=np.float64)
    xn = (xx - (width - 1) / 2.0) / max(1.0, width / 2.0)
    yn = (yy - (height - 1) / 2.0) / max(1.0, height / 2.0)
    radius = np.sqrt(xn * xn + yn * yn)
    dark_radius = radius[mask]
    outer_ink_fraction = (
        float(np.mean(dark_radius > 1.05)) if dark_radius.size else 1.0
    )
    edge_h = max(1, round(height * 0.22))
    edge_w = max(1, round(width * 0.22))
    top_ink = float(mask[:edge_h, :].mean())
    bottom_ink = float(mask[-edge_h:, :].mean())
    left_ink = float(mask[:, :edge_w].mean())
    right_ink = float(mask[:, -edge_w:].mean())
    corners = np.concatenate([
        mask[:edge_h, :edge_w].ravel(),
        mask[:edge_h, -edge_w:].ravel(),
        mask[-edge_h:, :edge_w].ravel(),
        mask[-edge_h:, -edge_w:].ravel(),
    ])
    corner_ink = float(corners.mean()) if corners.size else 0.0

    def _row_width_ratio(y: int) -> float:
        row = mask[max(0, min(height - 1, y))]
        positions = np.flatnonzero(row)
        if positions.size == 0:
            return 0.0
        return float((positions[-1] - positions[0] + 1) / max(1, width))

    return {
        "density": round(density, 4),
        "central_ink": round(central_ink, 4),
        "outer_ink_fraction": round(outer_ink_fraction, 4),
        "top_ink": round(top_ink, 4),
        "bottom_ink": round(bottom_ink, 4),
        "left_ink": round(left_ink, 4),
        "right_ink": round(right_ink, 4),
        "corner_ink": round(corner_ink, 4),
        "midrow_width": round(_row_width_ratio(height // 2), 4),
        "toprow_width": round(_row_width_ratio(max(0, round(height * 0.18))), 4),
        "bottomrow_width": round(_row_width_ratio(min(height - 1, round(height * 0.82))), 4),
    }


def _visual_family_symbol(
    deps: VisualEvidenceDeps, 
    inventory: dict[str, Any], family: str,
) -> tuple[str, str] | None:
    """Return (literal, role) for one configured visual family."""
    _SYMBOL_FAMILY_BY_LITERAL = deps._SYMBOL_FAMILY_BY_LITERAL
    for role, key in (("entry_marker", "entry_markers"), ("bracket_open", "bracket_openers")):
        for symbol in inventory.get(key, ()):
            if _SYMBOL_FAMILY_BY_LITERAL.get(str(symbol)) == family:
                return str(symbol), role
    return None


def _classify_visual_symbol_component(
    deps: VisualEvidenceDeps, 
    mask: np.ndarray,
    line_h: float,
    inventory: dict[str, Any],
) -> tuple[str, str, str, dict[str, float]] | None:
    """Classify a connected component only into configured symbol families."""
    _visual_marker_shape_metrics = deps._visual_marker_shape_metrics
    _visual_family_symbol = deps._visual_family_symbol
    height, width = mask.shape
    if width <= 0 or height <= 0:
        return None
    aspect = width / max(1.0, float(height))
    metrics = _visual_marker_shape_metrics(mask)
    density = float(metrics["density"])
    central = float(metrics["central_ink"])
    outer = float(metrics["outer_ink_fraction"])
    corner = float(metrics["corner_ink"])
    top = float(metrics["top_ink"])
    bottom = float(metrics["bottom_ink"])
    left = float(metrics["left_ink"])
    right = float(metrics["right_ink"])
    mid_width = float(metrics["midrow_width"])
    top_width = float(metrics["toprow_width"])
    bottom_width = float(metrics["bottomrow_width"])
    families = set(inventory.get("visual_families") or ())

    checks: list[tuple[str, bool]] = [
        ("circle_open",
         0.72 <= aspect <= 1.30
         and line_h * 0.78 <= width <= line_h * 1.30
         and line_h * 0.76 <= height <= line_h * 1.30
         and 0.22 <= density <= 0.42 and central <= 0.10 and outer <= 0.08),
        ("circle_filled",
         0.70 <= aspect <= 1.32
         and line_h * 0.46 <= width <= line_h * 1.16
         and line_h * 0.58 <= height <= line_h * 1.22
         and 0.60 <= density <= 0.94 and central >= 0.58 and outer <= 0.11),
        ("square_open",
         0.72 <= aspect <= 1.30
         and line_h * 0.55 <= height <= line_h * 1.30
         and 0.18 <= density <= 0.55 and central <= 0.18
         and min(top, bottom, left, right) >= 0.16 and corner >= 0.08),
        ("square_filled",
         0.72 <= aspect <= 1.30
         and line_h * 0.45 <= height <= line_h * 1.25
         and density >= 0.72 and central >= 0.70 and corner >= 0.45),
        ("diamond_open",
         0.70 <= aspect <= 1.35
         and line_h * 0.55 <= height <= line_h * 1.35
         and 0.14 <= density <= 0.50 and central <= 0.18
         and corner <= 0.16
         # A diamond widens much more sharply toward the mid-row than a ring.
         # This prevents a configured ◇ profile from accepting an unconfigured ○.
         and mid_width >= max(top_width, bottom_width) * 1.35),
        ("diamond_filled",
         0.70 <= aspect <= 1.35
         and line_h * 0.50 <= height <= line_h * 1.30
         and 0.45 <= density <= 0.82 and central >= 0.45
         and corner <= 0.32
         and mid_width >= max(top_width, bottom_width) * 1.35),
        ("triangle_open",
         0.65 <= aspect <= 1.50
         and line_h * 0.52 <= height <= line_h * 1.35
         and 0.12 <= density <= 0.48 and central <= 0.35
         and bottom_width >= top_width * 1.35),
        ("triangle_filled",
         0.65 <= aspect <= 1.50
         and line_h * 0.48 <= height <= line_h * 1.30
         and density >= 0.38 and central >= 0.35
         and bottom_width >= top_width * 1.25),
        ("bracket_open",
         0.18 <= aspect <= 0.95
         and line_h * 0.55 <= height <= line_h * 1.55
         and 0.12 <= density <= 0.68
         and max(left, right) >= 0.20
         and top >= 0.12 and bottom >= 0.12
         and central <= 0.60),
    ]
    for family, passed in checks:
        if family not in families or not passed:
            continue
        resolved = _visual_family_symbol(inventory, family)
        if resolved is None:
            continue
        symbol, role = resolved
        return family, symbol, role, metrics
    return None


def _trusted_visual_marker_lanes(
    deps: VisualEvidenceDeps, 
    lines: list[OCRLine],
    inventory: dict[str, Any],
    median_height: float,
) -> dict[str, dict[str, Any]]:
    """Derive stable marker lanes from OCR rows with explicit printed symbols.

    Bracket-like CJK radicals are common enough that candidate symbols must not
    define their own bracket lane.  When OCR explicitly sees the configured
    opener (for example 【) on at least two rows, those rows provide an
    independent X anchor for visual rescue.  Generic bracket shapes are then
    allowed only near this trusted lane.
    """
    if not bool(inventory.get("lane_required", False)):
        return {}

    openers = tuple(
        str(symbol)
        for symbol in inventory.get("bracket_openers", ())
        if str(symbol)
    )
    if not openers:
        return {}

    anchors: list[int] = []
    for line in lines:
        text = unicodedata.normalize("NFKC", str(line.text or "")).lstrip()
        if not any(text.startswith(opener) for opener in openers):
            continue
        try:
            anchors.append(int(line.box[0]))
        except (TypeError, ValueError):
            continue

    # One OCR row can itself be a segmentation outlier.  Two independent rows
    # are the minimum evidence required before generic shape rescue may use the
    # lane.  Template-only rescue remains available when no lane can be learned.
    if len(anchors) < 2:
        return {}

    line_h = max(8.0, float(median_height))
    configured_tolerance = (
        line_h
        * max(
            20,
            min(
                120,
                int(inventory.get("lane_tolerance_percent") or 50),
            ),
        )
        / 100.0
    )
    tolerance = max(8.0, min(configured_tolerance, line_h * 0.40))
    return {
        "bracket_open": {
            "x": round(float(np.median(np.asarray(anchors, dtype=float))), 2),
            "tolerance": round(float(tolerance), 2),
            "count": len(anchors),
            "source": "explicit_ocr_bracket_rows",
        }
    }


def _apply_trusted_visual_marker_lanes(
    deps: VisualEvidenceDeps, 
    candidates: list[dict[str, Any]],
    trusted_lanes: dict[str, dict[str, Any]] | None,
    *,
    template_threshold: float,
) -> list[dict[str, Any]]:
    """Filter ambiguous visual brackets against independent lane evidence.

    Generic bracket geometry is intentionally disabled when no trusted bracket
    lane exists: Chinese body glyphs contain too many bracket-like connected
    components.  A dictionary template may still rescue such a page, but when
    it is the sole evidence it must clear a conservative 0.70 floor.
    """
    lanes = dict(trusted_lanes or {})
    output: list[dict[str, Any]] = []
    for item in candidates:
        role = str(item.get("role") or "")
        if role != "bracket_open":
            output.append(item)
            continue

        lane = lanes.get(role)
        family = str(item.get("family") or "")
        if lane is None:
            if family != "dictionary_template":
                continue
            if float(item.get("template_score") or 0.0) < max(
                float(template_threshold), 0.70
            ):
                continue
            item["lane_required"] = True
            item["lane_source"] = "template_only_no_ocr_anchor"
            item["lane_anchor_count"] = 0
            output.append(item)
            continue

        lane_x = float(lane.get("x") or 0.0)
        tolerance = max(1.0, float(lane.get("tolerance") or 1.0))
        delta = abs(float(item.get("x0") or 0.0) - lane_x)
        if delta > tolerance:
            continue
        item["lane_x"] = round(lane_x, 2)
        item["lane_delta"] = round(delta, 2)
        item["lane_required"] = True
        item["lane_source"] = str(lane.get("source") or "trusted_lane")
        item["lane_anchor_count"] = int(lane.get("count") or 0)
        item["lane_tolerance"] = round(tolerance, 2)
        output.append(item)
    return output


def _detect_visual_entry_markers(
    deps: VisualEvidenceDeps, 
    gray: np.ndarray,
    median_height: float,
    left_limit: int,
    *,
    lower_bound: int = 0,
    inventory: dict[str, Any] | None = None,
    trusted_lanes: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Detect configured entry/bracket symbols directly from page pixels.

    The detector is dictionary-specific: only visual families implied by the
    active symbol inventory are considered. Unknown/custom literals remain OCR-
    only rather than being guessed from generic shapes.
    """
    _binary_rle_components = deps._binary_rle_components
    _visual_marker_shape_metrics = deps._visual_marker_shape_metrics
    _classify_visual_symbol_component = deps._classify_visual_symbol_component
    _apply_trusted_visual_marker_lanes = deps._apply_trusted_visual_marker_lanes
    _otsu_threshold = deps._otsu_threshold
    match_visual_marker_template = deps.match_visual_marker_template
    if gray.size == 0 or gray.ndim != 2:
        return []
    if inventory is None:
        # Low-level historical API/tests called this detector without a profile.
        # Keep that behavior as the original ○/● detector.
        inventory = {
            "enabled": True,
            "entry_markers": ("○", "●"),
            "bracket_openers": (),
            "visual_rescue": True,
            "lane_required": False,
            "lane_tolerance_percent": 50,
            "visual_families": ("circle_open", "circle_filled"),
        }
    else:
        inventory = dict(inventory)
    if not inventory.get("enabled", True) or not inventory.get("visual_rescue", True):
        return []
    templates = list(inventory.get("visual_templates") or [])
    template_mode = str(inventory.get("visual_template_mode") or "combined")
    template_enabled = bool(templates and template_mode != "off")
    if not inventory.get("visual_families") and not template_enabled:
        return []

    height, width = gray.shape
    line_h = max(8.0, float(median_height))
    zone_width = min(
        width,
        max(int(left_limit + round(line_h * 2.0)), round(line_h * 2.8), 56),
    )
    lower = max(0, min(height - 1, int(lower_bound)))
    if zone_width < 12 or lower >= height - 2:
        return []

    roi = gray[lower:, :zone_width]
    threshold = _otsu_threshold(roi)
    dark = roi <= threshold
    candidates: list[dict[str, Any]] = []
    broad_left = max(int(left_limit), round(line_h * 1.80))

    for x0, y0, x1, y1, _area in _binary_rle_components(dark):
        box_w = x1 - x0
        box_h = y1 - y0
        if box_w <= 0 or box_h <= 0 or x0 > broad_left:
            continue
        component = dark[y0:y1, x0:x1]
        classified = None
        template_match = None
        if (
            template_enabled
            and line_h * 0.24 <= box_h <= line_h * 1.85
            and line_h * 0.16 <= box_w <= line_h * 1.85
        ):
            try:
                template_match = match_visual_marker_template(component, templates)
            except ValueError:
                template_match = None
            if (
                template_match is not None
                and float(template_match.get("score") or 0.0)
                >= float(inventory.get("visual_template_threshold") or 0.68)
            ):
                sample = dict(template_match.get("sample") or {})
                role = str(sample.get("role") or "")
                source = (
                    inventory.get("entry_markers")
                    if role == "entry_marker"
                    else inventory.get("bracket_openers")
                )
                configured_symbol = str(next(iter(source or ()), ""))
                sample_symbol = str(sample.get("literal") or "")
                if str(inventory.get("visual_template_group_mode") or "role") == "literal":
                    symbol = sample_symbol or configured_symbol
                else:
                    symbol = configured_symbol or sample_symbol
                if role == "entry_marker" or (role == "bracket_open" and symbol):
                    classified = (
                        "dictionary_template",
                        symbol,
                        role,
                        _visual_marker_shape_metrics(component),
                    )

        # In template-first mode a configured template set is authoritative:
        # generic circle/square/triangle families are retained only when no
        # templates exist. Combined mode uses the old family detector as a
        # fallback when template similarity is insufficient.
        if classified is None and not (template_enabled and template_mode == "template_first"):
            classified = _classify_visual_symbol_component(
                component, line_h, inventory
            )
        if classified is None:
            continue
        family, symbol, role, metrics = classified
        legacy_type = {
            "circle_open": "open_circle",
            "circle_filled": "filled_circle",
            "dictionary_template": "visual_template",
        }.get(family, family)
        item: dict[str, Any] = {
            "type": legacy_type, "family": family, "symbol": symbol, "role": role,
            "x0": int(x0), "x1": int(x1),
            "y0": int(lower + y0), "y1": int(lower + y1),
            "center_y": round(float(lower + (y0 + y1) / 2.0), 2),
            "width": int(box_w), "height": int(box_h),
            "threshold": int(threshold),
        }
        item.update(metrics)
        if family == "dictionary_template" and template_match is not None:
            matched_sample = dict(template_match.get("sample") or {})
            item["template_score"] = float(template_match.get("score") or 0.0)
            item["template_iou"] = float(template_match.get("iou") or 0.0)
            item["template_projection"] = float(
                template_match.get("projection") or 0.0
            )
            item["template_sample_id"] = str(matched_sample.get("id") or "")
            item["template_source_page"] = str(
                matched_sample.get("source_page") or ""
            )
            item["template_literal"] = str(matched_sample.get("literal") or "")
        candidates.append(item)

    if not candidates:
        return []

    candidates = _apply_trusted_visual_marker_lanes(
        candidates,
        trusted_lanes,
        template_threshold=float(
            inventory.get("visual_template_threshold") or 0.68
        ),
    )
    if not candidates:
        return []

    # Lane filtering is role-aware. A dictionary can therefore keep one marker
    # lane for ○/● and a nearby bracket lane without forcing both onto one X.
    # Brackets with an explicit-OCR trusted lane were already filtered above;
    # do not let surviving candidates vote themselves into a different lane.
    if bool(inventory.get("lane_required", False)):
        tolerance = max(
            6.0,
            line_h * max(20, min(120, int(inventory.get("lane_tolerance_percent") or 50))) / 100.0,
        )
        filtered: list[dict[str, Any]] = []
        for role in ("entry_marker", "bracket_open"):
            group = [item for item in candidates if item.get("role") == role]
            if not group:
                continue
            if role in (trusted_lanes or {}):
                filtered.extend(group)
                continue
            if len(group) >= 3:
                lane_x = float(np.median([item["x0"] for item in group]))
                group = [
                    item for item in group
                    if abs(float(item["x0"]) - lane_x) <= tolerance
                ]
                for item in group:
                    item["lane_x"] = round(lane_x, 2)
                    item["lane_delta"] = round(abs(float(item["x0"]) - lane_x), 2)
                    item["lane_required"] = True
            filtered.extend(group)
        candidates = filtered
    return candidates


def _match_visual_entry_markers_to_lines(
    deps: VisualEvidenceDeps, 
    lines: list[OCRLine],
    markers: list[dict[str, Any]],
    median_height: float,
) -> dict[int, dict[str, Any]]:
    """Pair visual ○/● markers with OCR rows on the same physical line."""
    if not lines or not markers:
        return {}
    line_h = max(8.0, float(median_height))
    max_delta = max(8.0, line_h * 0.80)
    proposals: list[tuple[float, int, int]] = []
    for marker_index, marker in enumerate(markers):
        marker_center = float(marker["center_y"])
        marker_x1 = int(marker["x1"])
        for line_index, line in enumerate(lines):
            x0, y0, _x1, y1 = line.box
            line_center = (y0 + y1) / 2.0
            delta = abs(line_center - marker_center)
            if delta > max_delta:
                continue
            if x0 > marker_x1 + line_h * 3.2:
                continue
            overlap = max(
                0, min(int(marker["y1"]), y1) - max(int(marker["y0"]), y0)
            )
            if overlap <= 0 and delta > line_h * 0.55:
                continue
            proposals.append((delta, marker_index, line_index))

    matches: dict[int, dict[str, Any]] = {}
    used_markers: set[int] = set()
    used_lines: set[int] = set()
    for delta, marker_index, line_index in sorted(proposals):
        if marker_index in used_markers or line_index in used_lines:
            continue
        item = dict(markers[marker_index])
        item["match_method"] = "visual_marker_nearest_row"
        item["ocr_line_index"] = int(line_index)
        item["center_delta"] = round(float(delta), 2)
        matches[line_index] = item
        used_markers.add(marker_index)
        used_lines.add(line_index)
    return matches


def _parse_cjk_visual_marker_line(
    deps: VisualEvidenceDeps, 
    text: str,
    marker_symbol: str,
    settings: AppSettings,
    profile: DictionaryProfile,
) -> HeadwordParse | None:
    """Recover a marker-led CJK head when OCR omitted/misread the visual marker.

    The visual template itself supplies the entry-boundary evidence, so this
    rescue path does not require OCR to recover the configured Unicode marker.
    """
    _is_chinese_ocr = deps._is_chinese_ocr
    _repair_headword_ocr = deps._repair_headword_ocr
    if not _is_chinese_ocr(settings):
        return None
    parse_text, repairs = _repair_headword_ocr(text)
    # At most a few OCR junk glyphs may precede the Han lemma where the printed
    # marker was. Keep the same compact CJK lemma grammar as marker-prefixed OCR.
    match = re.search(
        r"(?P<lemma>[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
        r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaffA-Za-z0-9·-]{0,23})",
        parse_text[:72],
    )
    if match is None or match.start("lemma") > 4:
        return None
    raw = match.group("lemma")
    normalized = unicodedata.normalize("NFKC", raw).strip()
    marker_label = marker_symbol or "visual-template"
    return HeadwordParse(
        raw=raw,
        normalized=normalized,
        has_pos=False,
        pos_text="",
        has_inflection=False,
        inflection_text="",
        has_descriptor=True,
        descriptor_text="cjk_marker_pinyin",
        match_end=max(1, match.end("lemma")),
        looks_like_continuation=False,
        continuation_reason="",
        corrected_raw=raw,
        parse_text=parse_text,
        ocr_repairs=tuple(repairs),
        variants=(),
        plural_text="",
        usage_text="",
        definition_text=parse_text[match.end("lemma"):].strip(),
        parser_stage="cjk_visual_marker_rescue",
        parser_trace=(
            f"visual_entry_marker:{marker_label}",
            "cjk_visual_marker_rescue",
        ),
        bug_types=(),
    )


def _parse_visual_configured_symbol_line(
    deps: VisualEvidenceDeps, 
    text: str,
    visual_symbol: dict[str, Any],
    settings: AppSettings,
    profile: DictionaryProfile,
) -> HeadwordParse | None:
    """Recover a configured fixed-symbol head when OCR lost the symbol itself."""
    _parse_cjk_visual_marker_line = deps._parse_cjk_visual_marker_line
    _is_chinese_ocr = deps._is_chinese_ocr
    _repair_headword_ocr = deps._repair_headword_ocr
    _parse_chinese_bracketed_headword = deps._parse_chinese_bracketed_headword
    _is_japanese_ocr = deps._is_japanese_ocr
    _BRACKET_CLOSER_BY_OPENER = deps._BRACKET_CLOSER_BY_OPENER
    role = str(visual_symbol.get("role") or "")
    symbol = str(visual_symbol.get("symbol") or "")
    if role == "entry_marker":
        return _parse_cjk_visual_marker_line(text, symbol, settings, profile)
    if role != "bracket_open" or not symbol:
        return None

    parse_text, _repairs = _repair_headword_ocr(text)
    closer = _BRACKET_CLOSER_BY_OPENER.get(symbol, "")
    # When OCR dropped the opening bracket, require either a visible matching
    # closer or a short headword-like physical row.  This keeps a visual bracket
    # component from swallowing a long definition line.
    has_closer = bool(closer and closer in parse_text[:72])
    compact = parse_text.strip()
    if not has_closer and len(compact) > 24:
        return None

    match = re.search(
        r"[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]",
        parse_text[:16],
    )
    if match is None or match.start() > 6:
        return None
    synthetic = symbol + parse_text[match.start():]
    parsed = _parse_chinese_bracketed_headword(
        synthetic,
        settings,
        enforce_chinese_language=not (
            _is_chinese_ocr(settings) or _is_japanese_ocr(settings)
        ),
        allow_japanese_reading_prefix=False,
        allowed_openers=(symbol,),
    )
    if parsed is None:
        return None
    parsed.parser_stage = "cjk_visual_bracket_rescue"
    parsed.parser_trace = (
        f"visual_headword_symbol:{symbol}",
        "cjk_visual_bracket_rescue",
    )
    return parsed


def _leading_cjk_ideograph(
    deps: VisualEvidenceDeps, text: str) -> str:
    """Return a CJK glyph only when it is the actual leading token.

    This helper is used only inside visually localized oversized-CJK rescue.
    Besides pinyin/variant tails it accepts a compact sense-number suffix such
    as 案1 / 暗2 (circled digits normalize to ASCII digits under NFKC). The
    image-level oversized-run gate remains mandatory.
    """
    _is_single_cjk_ideograph = deps._is_single_cjk_ideograph
    normalized = unicodedata.normalize("NFKC", text or "").lstrip()
    if not normalized or not _is_single_cjk_ideograph(normalized[0]):
        return ""
    tail = normalized[1:].lstrip()
    if not tail:
        return normalized[0]
    first_tail = tail[0]
    if _is_single_cjk_ideograph(first_tail):
        return ""
    if first_tail.isalpha():
        return normalized[0]
    sense = re.match(r"^\d{1,2}(?=$|\s|\(|\[|（|［|/|·|,|，|:|：|\.|-)", tail)
    if sense is not None:
        remainder = tail[sense.end():].lstrip(" \t([（［/·,，:：.-")
        if not remainder or not _is_single_cjk_ideograph(remainder[0]):
            return normalized[0]
    if first_tail in "([（［/·,，:：":
        remainder = tail[1:].lstrip(" \t([（［/·,，:：")
        if not remainder or (
            remainder[0].isalpha()
            and not _is_single_cjk_ideograph(remainder[0])
        ):
            return normalized[0]
    return ""

def _cjk_visual_projection_runs(
    deps: VisualEvidenceDeps, 
    gray: np.ndarray,
    header_cutoff: int,
    settings: AppSettings,
    pixel_scale: float,
    *,
    relaxed: bool = False,
) -> tuple[int, list[tuple[int, int]]]:
    """Locate oversized single-character rows from image geometry alone.

    Chinese character dictionaries often print single-character entries at
    roughly twice the body-text height while compound entries use ordinary-size
    bracketed lines.  OCR segmentation can merge the large glyph with nearby
    pronunciation/variant text, so a left-strip row projection is a more stable
    way to recover the entry Y position.  This detector does *not* decide the
    word; it only supplies visual runs that must still be associated with OCR.
    """
    _otsu_threshold = deps._otsu_threshold
    _true_runs = deps._true_runs
    if gray.size == 0:
        return 0, []
    ratio = max(0.25, float(pixel_scale))
    zone_width = min(gray.shape[1], max(48, round(100 * ratio)))
    if zone_width <= 0:
        return 0, []
    threshold = _otsu_threshold(gray[:, :zone_width])
    dark_counts = (gray[:, :zone_width] <= threshold).sum(axis=1)
    active = dark_counts >= max(3, round(zone_width * 0.015))

    # Fill only tiny vertical holes inside a glyph.  Do not bridge the whitespace
    # between ordinary dictionary lines.
    max_gap = max(2, round(2.2 * ratio))
    active_list = active.tolist()
    index = 0
    while index < len(active_list):
        if active_list[index]:
            index += 1
            continue
        end = index
        while end < len(active_list) and not active_list[end]:
            end += 1
        if index > 0 and end < len(active_list) and end - index <= max_gap:
            active_list[index:end] = [True] * (end - index)
        index = end

    runs = _true_runs(np.asarray(active_list, dtype=bool))
    runtime_width = max(1, int(gray.shape[1]))
    expected_body = max(
        8.0,
        float(settings.character_height),
    )
    body_heights = [
        end - start for start, end in runs
        if expected_body * 0.45 <= end - start <= expected_body * 1.55
    ]
    if body_heights:
        body_median = float(np.median(np.asarray(body_heights, dtype=float)))
    else:
        plausible = [end - start for start, end in runs if end - start >= max(6, round(5 * ratio))]
        body_median = float(np.median(np.asarray(plausible, dtype=float))) if plausible else expected_body

    if relaxed:
        # Discovery is deliberately high-recall; final promotion still requires
        # a tightly cropped local OCR result that resolves to one Han headword.
        # A lower-distribution reference prevents consecutive display heads from
        # inflating the page median and hiding one another.
        raw_body_reference = (
            float(np.percentile(np.asarray(body_heights, dtype=float), 35))
            if body_heights else body_median
        )
        # The left strip of a character dictionary may contain almost nothing
        # except display heads. Cap the discovery reference at the configured
        # ordinary line height so a page full of consecutive large glyphs does
        # not redefine "normal" upward and hide the smaller display heads.
        body_reference = min(raw_body_reference, expected_body)
        minimum_large = max(body_reference * 1.28, expected_body * 1.25)
        maximum_large = max(
            minimum_large + 1.0,
            body_reference * 4.2,
            expected_body * 4.0,
        )
    else:
        minimum_large = max(body_median * 1.45, expected_body * 1.55)
        maximum_large = max(minimum_large + 1.0, body_median * 3.6)
    result: list[tuple[int, int]] = []
    for start, end in runs:
        height = end - start
        if start < header_cutoff:
            continue
        if height < minimum_large or height > maximum_large:
            continue
        result.append((start, end))
    return zone_width, result


def _cjk_right_context_metrics(
    deps: VisualEvidenceDeps, 
    gray: np.ndarray,
    run: tuple[int, int],
    zone_width: int,
    settings: AppSettings,
    *,
    header_cutoff: int = 0,
) -> dict[str, Any]:
    """Measure whitespace/sparsity immediately to the right of a large CJK run.

    Many dictionary designs give an oversized head character a locally sparse
    right side: pronunciation may occupy the upper part, while the lower/right
    area remains much emptier than ordinary body text.  The sampled width scales
    with the detected run height rather than fixed pixels so the cue survives DPI
    changes.  This is supporting evidence, never a standalone headword decision.
    """
    _otsu_threshold = deps._otsu_threshold
    enabled = bool(
        getattr(settings, "profile_cjk_right_context_enabled", True)
    )
    width_percent = max(
        30,
        min(
            200,
            int(getattr(settings, "profile_cjk_right_context_width_percent", 80) or 80),
        ),
    )
    metrics: dict[str, Any] = {
        "enabled": enabled,
        "available": False,
        "sparse": False,
        "width_percent": width_percent,
        "width_px": 0,
        "blank_ratio": 0.0,
        "lower_blank_ratio": 0.0,
        "row_occupancy": 1.0,
        "ink_density": 1.0,
        "baseline_ink_density": 0.0,
        "density_ratio": 1.0,
        "sparse_votes": 0,
    }
    if not enabled or gray.size == 0:
        return metrics

    image_h, image_w = gray.shape[:2]
    start = max(0, min(image_h, int(run[0])))
    end = max(start + 1, min(image_h, int(run[1])))
    run_height = max(1, end - start)
    x0 = max(0, min(image_w, int(zone_width)))
    requested = max(8, round(run_height * width_percent / 100.0))
    x1 = min(image_w, x0 + requested)
    if x1 - x0 < 6:
        return metrics

    analysis_top = max(0, min(image_h, int(header_cutoff)))
    threshold_source = gray[analysis_top:, x0:x1]
    if threshold_source.size == 0:
        threshold_source = gray[:, x0:x1]
    threshold = _otsu_threshold(threshold_source)

    roi = gray[start:end, x0:x1]
    if roi.size == 0:
        return metrics
    dark = roi <= threshold
    ink_density = float(np.mean(dark))
    blank_ratio = 1.0 - ink_density

    lower_offset = max(0, min(dark.shape[0] - 1, round(dark.shape[0] * 0.35)))
    lower = dark[lower_offset:, :]
    lower_blank_ratio = (
        1.0 - float(np.mean(lower)) if lower.size else blank_ratio
    )
    row_dark_counts = dark.sum(axis=1)
    row_ink_floor = max(1, round(dark.shape[1] * 0.035))
    row_occupancy = float(np.mean(row_dark_counts >= row_ink_floor))

    baseline_parts: list[np.ndarray] = []
    if start > analysis_top:
        baseline_parts.append(gray[analysis_top:start, x0:x1])
    if end < image_h:
        baseline_parts.append(gray[end:image_h, x0:x1])
    baseline = (
        np.concatenate(baseline_parts, axis=0)
        if baseline_parts else np.empty((0, x1 - x0), dtype=gray.dtype)
    )
    if baseline.size:
        baseline_ink_density = float(np.mean(baseline <= threshold))
    else:
        baseline_ink_density = 0.0
    density_ratio = (
        ink_density / max(0.01, baseline_ink_density)
        if baseline_ink_density > 0
        else 1.0
    )

    votes = 0
    if blank_ratio >= 0.78:
        votes += 1
    if lower_blank_ratio >= 0.86:
        votes += 1
    if row_occupancy <= 0.50:
        votes += 1
    if baseline_ink_density >= 0.02 and density_ratio <= 0.60:
        votes += 1
    sparse = bool(lower_blank_ratio >= 0.80 and votes >= 2)

    metrics.update({
        "available": True,
        "sparse": sparse,
        "width_px": int(x1 - x0),
        "blank_ratio": round(blank_ratio, 4),
        "lower_blank_ratio": round(lower_blank_ratio, 4),
        "row_occupancy": round(row_occupancy, 4),
        "ink_density": round(ink_density, 4),
        "baseline_ink_density": round(baseline_ink_density, 4),
        "density_ratio": round(density_ratio, 4),
        "sparse_votes": int(votes),
    })
    return metrics


def _cjk_right_context_features(
    deps: VisualEvidenceDeps, metrics: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten right-context diagnostics into JSON-safe candidate features."""
    if not metrics:
        return {}
    return {
        "cjk_right_context_enabled": bool(metrics.get("enabled", False)),
        "cjk_right_context_available": bool(metrics.get("available", False)),
        "cjk_right_context_sparse": bool(metrics.get("sparse", False)),
        "cjk_right_context_width_percent": int(metrics.get("width_percent", 0) or 0),
        "cjk_right_context_width_px": int(metrics.get("width_px", 0) or 0),
        "cjk_right_blank_ratio": float(metrics.get("blank_ratio", 0.0) or 0.0),
        "cjk_lower_right_blank_ratio": float(
            metrics.get("lower_blank_ratio", 0.0) or 0.0
        ),
        "cjk_right_row_occupancy": float(
            metrics.get("row_occupancy", 0.0) or 0.0
        ),
        "cjk_right_density_ratio": float(
            metrics.get("density_ratio", 1.0) or 1.0
        ),
        "cjk_right_sparse_votes": int(metrics.get("sparse_votes", 0) or 0),
    }


def _cjk_candidate_right_context_metrics(
    deps: VisualEvidenceDeps, 
    gray: np.ndarray,
    box: tuple[int, int, int, int],
    median_height: float,
    settings: AppSettings,
    *,
    header_cutoff: int = 0,
) -> dict[str, Any]:
    """Right-side layout evidence centered on an OCR single-Han candidate.

    This is the second path for large-head detection: it does not require the
    left-strip projection to have produced an oversized run first.  OCR can crop
    a real display glyph to body height, so estimate a plausible display-height
    window from the page-local median and inspect the area immediately to the
    right of the candidate itself.
    """
    _cjk_right_context_metrics = deps._cjk_right_context_metrics
    x0, y0, x1, y1 = (int(value) for value in box)
    box_height = max(1, y1 - y0)
    expected_height = max(box_height, round(max(1.0, median_height) * 1.45))
    center_y = (y0 + y1) / 2.0
    run_start = round(center_y - expected_height / 2.0)
    run_end = run_start + expected_height
    image_h, image_w = gray.shape[:2]
    if run_start < header_cutoff:
        run_end += header_cutoff - run_start
        run_start = header_cutoff
    if run_end > image_h:
        run_start = max(header_cutoff, run_start - (run_end - image_h))
        run_end = image_h

    # Start at the candidate's own right edge.  For very narrow/clipped boxes,
    # keep at least a modest glyph-width estimate so we do not sample through
    # the right half of the Han character itself.
    estimated_glyph_width = max(
        box_height,
        round(max(1.0, median_height) * 0.78),
    )
    context_x = max(x1, x0 + estimated_glyph_width)
    context_x = min(max(0, context_x), image_w)
    metrics = _cjk_right_context_metrics(
        gray,
        (run_start, run_end),
        context_x,
        settings,
        header_cutoff=header_cutoff,
    )
    metrics["candidate_box_height"] = int(box_height)
    metrics["candidate_expected_height"] = int(expected_height)
    metrics["candidate_context_x"] = int(context_x)
    metrics["candidate_run_start"] = int(run_start)
    metrics["candidate_run_end"] = int(run_end)
    metrics["candidate_baseline_supported"] = bool(
        float(metrics.get("baseline_ink_density", 0.0) or 0.0) >= 0.01
    )
    return metrics


def _cjk_candidate_right_context_features(
    deps: VisualEvidenceDeps, 
    metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Candidate-local right-context diagnostics with a non-colliding prefix."""
    if not metrics:
        return {}
    return {
        "cjk_candidate_right_context_available": bool(
            metrics.get("available", False)
        ),
        "cjk_candidate_right_context_sparse": bool(metrics.get("sparse", False)),
        "cjk_candidate_right_blank_ratio": float(
            metrics.get("blank_ratio", 0.0) or 0.0
        ),
        "cjk_candidate_lower_right_blank_ratio": float(
            metrics.get("lower_blank_ratio", 0.0) or 0.0
        ),
        "cjk_candidate_right_row_occupancy": float(
            metrics.get("row_occupancy", 0.0) or 0.0
        ),
        "cjk_candidate_right_density_ratio": float(
            metrics.get("density_ratio", 1.0) or 1.0
        ),
        "cjk_candidate_right_sparse_votes": int(
            metrics.get("sparse_votes", 0) or 0
        ),
        "cjk_candidate_right_context_x": int(
            metrics.get("candidate_context_x", 0) or 0
        ),
        "cjk_candidate_expected_height": int(
            metrics.get("candidate_expected_height", 0) or 0
        ),
    }


def _cjk_word_for_visual_run(
    deps: VisualEvidenceDeps, 
    records: list[OCRRecord],
    run: tuple[int, int],
    zone_width: int,
    settings: AppSettings,
    profile: DictionaryProfile | None = None,
    right_context: dict[str, Any] | None = None,
) -> tuple[str, float, OCRRecord | None]:
    """Pick an OCR token that physically represents one oversized CJK glyph.

    The active Project Profile is passed through so a short ``漢字 + pinyin``
    OCR record can use the same structural parser as the ordinary OCR channel.
    This matters when OCR crops the large glyph vertically: strong profile
    structure may safely relax the visual-box gate, while unparsed fallback
    candidates remain deliberately strict.
    """
    _leading_cjk_ideograph = deps._leading_cjk_ideograph
    _is_single_cjk_ideograph = deps._is_single_cjk_ideograph
    parse_headword_text = deps.parse_headword_text
    _parse_cjk_single_with_pinyin = deps._parse_cjk_single_with_pinyin
    start, end = run
    center = (start + end) / 2.0
    height = max(1, end - start)
    ranked: list[tuple[float, int, float, str, OCRRecord]] = []
    for record in records:
        x0, y0, x1, y1 = record.box
        if x0 > zone_width * 1.12:
            continue
        record_height = max(1, y1 - y0)
        record_width = max(1, x1 - x0)
        overlap = max(0, min(end, y1) - max(start, y0))
        record_center = (y0 + y1) / 2.0
        distance = abs(record_center - center)

        parsed = parse_headword_text(record.text, settings, profile=profile)
        profile_pinyin = None
        parser_controls = int(
            getattr(settings, "profile_parser_controls_version", 0) or 0
        ) >= 1
        single_enabled = (
            bool(getattr(settings, "profile_cjk_allow_single_headword", True))
            if parser_controls else True
        )
        if single_enabled:
            # "大字单字" is the user-facing Project Profile contract.  Inside an
            # already detected oversized visual run, a record that starts with
            # one Han glyph plus romanization is strong structure even when the
            # generic parser/profile metadata did not return a parsed object.
            # The compact-width and overlap gates below still prevent ordinary
            # definition lines from using this relaxed path.
            profile_pinyin = _parse_cjk_single_with_pinyin(record.text, settings)
        if profile_pinyin is not None:
            parsed = profile_pinyin
        parsed_single = bool(
            parsed and _is_single_cjk_ideograph(parsed.normalized)
        )
        profile_pinyin_single = bool(
            profile_pinyin is not None and parsed_single
        )
        profile_visual_single = bool(
            parsed_single
            and single_enabled
            and profile is not None
            and profile.family == "cjk_visual"
            and parsed is not None
            and parsed.parser_stage in {
                "chinese_single_character",
                "chinese_single_character_with_variant",
            }
        )
        word = parsed.normalized if parsed_single else _leading_cjk_ideograph(record.text)
        if not word:
            continue

        context_available = bool(
            right_context and right_context.get("available")
        )
        context_sparse = bool(
            right_context and right_context.get("sparse")
        )
        if profile_pinyin_single or profile_visual_single:
            # Strong Project-Profile structure plus a sparse right-side layout is
            # especially characteristic of a real display head.  It safely buys
            # a little extra recall when OCR vertically clips the glyph.  If the
            # right side is dense, keep a slightly stricter box gate rather than
            # rejecting the otherwise strong OCR structure outright.
            if context_sparse:
                minimum_height_ratio = 0.24
                overlap_ratio = 0.18
                distance_ratio = 0.76
            elif context_available:
                minimum_height_ratio = 0.30
                overlap_ratio = 0.24
                distance_ratio = 0.70
            else:
                # Backward-compatible neutral behavior for callers/caches that
                # do not yet carry right-context metrics.
                minimum_height_ratio = 0.28
                overlap_ratio = 0.22
                distance_ratio = 0.72
            if record_width > zone_width * 1.75:
                continue
            if distance > height * distance_ratio:
                continue
        elif parsed_single:
            minimum_height_ratio = 0.40
            overlap_ratio = 0.30
        else:
            # Weak fallback evidence should not be rescued from a dense block of
            # ordinary body text when the right-context measurement is available.
            if context_available and not context_sparse:
                continue
            minimum_height_ratio = 0.55
            overlap_ratio = 0.45

        # OCR boxes are integer-valued; allow half a pixel of quantization
        # tolerance at an exact ratio boundary (e.g. 14 px / 50 px = 0.28).
        if record_height + 0.5 < height * minimum_height_ratio:
            continue
        overlap_floor = min(record_height, height) * overlap_ratio
        if overlap < overlap_floor:
            continue

        # The unparsed fallback is intentionally stricter: it must start inside
        # the left visual zone instead of merely containing a Han character.
        if not parsed_single and x0 > zone_width * 0.95:
            continue

        quality_rank = 0 if profile_pinyin_single else (1 if parsed_single else 2)
        ranked.append((distance, quality_rank, -float(record.confidence), word, record))
    if not ranked:
        return "", 0.0, None
    ranked.sort(key=lambda item: (item[1], item[0], item[2]))
    _distance, _quality, _neg_conf, word, record = ranked[0]
    return word, float(record.confidence), record

