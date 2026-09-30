from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from .image_utils import normalize_page_rgb
from .layout_transform import LayoutTransform
from .models import AppSettings


def _box_sum(mask: np.ndarray, radius_y: int, radius_x: int) -> np.ndarray:
    """Return a fast local foreground count with the same shape as *mask*."""
    ry = max(0, int(radius_y))
    rx = max(0, int(radius_x))
    src = np.pad(mask.astype(np.uint8, copy=False), ((ry, ry), (rx, rx)), mode="constant")
    integral = np.pad(src.cumsum(axis=0, dtype=np.int32).cumsum(axis=1, dtype=np.int32), ((1, 0), (1, 0)))
    height = 2 * ry + 1
    width = 2 * rx + 1
    return (
        integral[height:, width:]
        - integral[:-height, width:]
        - integral[height:, :-width]
        + integral[:-height, :-width]
    )


def clean_layout_speckles(image: Image.Image, settings: AppSettings, backend: Any) -> Image.Image:
    """Remove only tiny isolated dark specks from the image used for layout analysis.

    This deliberately does not touch the image consumed by VB/headword OCR. Long
    vertical/horizontal strokes are protected so dictionary rules, separators and
    glyph stems survive even when they are only one or two pixels thick.
    """
    source = normalize_page_rgb(image)
    gray = np.asarray(ImageOps.grayscale(source), dtype=np.uint8)
    ink = backend._analysis_ink_mask(gray, settings)
    if ink.size == 0 or not np.any(ink):
        return source.copy()

    local5 = _box_sum(ink, 2, 2)
    local11 = _box_sum(ink, 5, 5)
    vertical13 = _box_sum(ink, 6, 0)
    horizontal13 = _box_sum(ink, 0, 6)
    remove = (
        ink
        & (local5 <= 6)
        & (local11 <= 10)
        & (vertical13 < 6)
        & (horizontal13 < 6)
    )
    if not np.any(remove):
        return source.copy()

    arr = np.asarray(source).copy()
    arr[remove] = 255
    return Image.fromarray(arr, mode="RGB")


def _closeness(a: float, b: float, scale: float) -> float:
    scale = max(1.0, float(scale))
    return max(0.0, 1.0 - abs(float(a) - float(b)) / scale)


def _choose_geometry_value(
    primary: int,
    secondary: int,
    reference: int,
    *,
    scale: float,
    pair_tolerance: float,
    reference_tolerance: float,
) -> tuple[int, bool]:
    p = int(primary)
    s = int(secondary)
    r = int(reference)
    unit = max(1.0, float(scale))
    if abs(p - s) <= pair_tolerance * unit:
        merged = round((p + s) / 2)
        if abs(merged - r) <= reference_tolerance * unit:
            return merged, False
    p_dev = abs(p - r) / unit
    s_dev = abs(s - r) / unit
    if p_dev <= reference_tolerance and (p_dev <= s_dev or s_dev > reference_tolerance):
        return p, False
    if s_dev <= reference_tolerance:
        return s, False
    return r, True


def _merge_start_y(primary: int, secondary: int, height: int, character_height: int) -> int:
    # Header/title pages legitimately move start_y by hundreds of pixels, so do
    # not compare start_y with the project default.
    tolerance = max(character_height * 3, round(height * 0.08), 12)
    if abs(int(primary) - int(secondary)) <= tolerance:
        return max(0, round((int(primary) + int(secondary)) / 2))
    return max(0, int(primary))


def _separator_track(
    ink: np.ndarray,
    *,
    expected_x: int,
    pitch: int,
    body_top: int,
    body_bottom: int,
) -> tuple[int, float] | None:
    """Track a long vertical separator while tolerating small scan curvature."""
    if ink.ndim != 2 or ink.shape[0] < 20 or ink.shape[1] < 20:
        return None
    top = max(0, min(ink.shape[0] - 2, int(body_top)))
    bottom = max(top + 2, min(ink.shape[0], int(body_bottom)))
    if bottom - top < max(40, ink.shape[0] * 0.12):
        top = max(0, round(ink.shape[0] * 0.05))
        bottom = min(ink.shape[0], round(ink.shape[0] * 0.97))

    radius = max(12, round(max(20, pitch) * 0.10))
    left = max(0, int(expected_x) - radius)
    right = min(ink.shape[1], int(expected_x) + radius + 1)
    if right - left < 5:
        return None

    blocks = [b for b in np.array_split(ink[top:bottom, left:right], 20, axis=0) if b.shape[0] >= 3]
    xs: list[int] = []
    peaks: list[float] = []
    for block in blocks:
        density = block.mean(axis=0)
        if density.size < 3:
            continue
        smooth = np.convolve(density, np.ones(3, dtype=float) / 3.0, mode="same")
        idx = int(np.argmax(smooth))
        peak = float(smooth[idx])
        if peak < 0.20:
            continue
        xs.append(left + idx)
        peaks.append(peak)

    if not blocks or len(xs) < max(6, round(len(blocks) * 0.50)):
        return None
    center = float(np.median(xs))
    deviations = np.abs(np.asarray(xs, dtype=float) - center)
    spread = float(np.percentile(deviations, 90)) if deviations.size else 999.0
    if abs(center - expected_x) > max(10.0, pitch * 0.13):
        return None
    if spread > max(7.0, pitch * 0.025):
        return None

    coverage = len(xs) / max(1, len(blocks))
    peak_score = min(1.0, float(np.median(peaks)) / 0.55)
    spread_score = max(0.0, 1.0 - spread / max(8.0, pitch * 0.03))
    score = max(0.0, min(1.0, 0.50 * coverage + 0.35 * peak_score + 0.15 * spread_score))
    if score < 0.55:
        return None
    return round(center), score


def _reference_starts(settings: AppSettings) -> tuple[int, ...]:
    count = max(1, int(settings.columns))
    pitch = max(1, int(settings.column_width) + int(settings.gutter))
    x0 = max(0, int(settings.manual_x))
    return tuple(x0 + i * pitch for i in range(count))


def _projection_estimate(cleaned_source: Image.Image, settings: AppSettings, backend: Any) -> Any:
    canonical = LayoutTransform(settings.layout_transform).canonical_image_for_analysis(cleaned_source)
    estimate = backend._projection_layout_estimate(canonical, settings)
    estimate.canonical_transform = LayoutTransform(settings.layout_transform).kind
    return estimate


def _paddle_estimate(cleaned_source: Image.Image, settings: AppSettings, backend: Any) -> Any:
    """Run the normal Paddle layout path, without treating successful execution as reliability."""
    transform = LayoutTransform(settings.layout_transform)
    analysis = transform.canonical_image_for_analysis(cleaned_source)
    detector = backend._get_text_detector(settings)
    import os

    os.environ["FLAGS_enable_pir_api"] = "0"
    try:
        results = list(detector.predict(np.asarray(analysis), batch_size=1, limit_side_len=2400))
    except TypeError:
        results = list(detector.predict(np.asarray(analysis)))
    if not results:
        raise RuntimeError("PaddleOCR 整页版面检测没有返回结果。")
    boxes = backend._boxes_from_detection(results[0], analysis.width, analysis.height)
    if not boxes:
        raise RuntimeError("PaddleOCR 整页版面检测没有返回文本框。")
    gray = np.asarray(ImageOps.grayscale(analysis), dtype=np.uint8)
    estimate = backend.infer_layout_from_boxes(
        boxes,
        analysis.size,
        display_scale=1.0,
        ink_mask=backend._analysis_ink_mask(gray, settings),
        columns_policy=settings.layout_columns_policy,
        fixed_columns=settings.columns,
        column_separator_mode=settings.layout_column_separator_mode,
    )
    estimate.canonical_transform = transform.kind
    return estimate


def _fuse_fixed_geometry(
    primary: Any,
    secondary: Any,
    settings: AppSettings,
    cleaned_source: Image.Image,
    backend: Any,
) -> Any:
    """Fuse two current-page estimates against a fixed project geometry prior."""
    width, height = cleaned_source.size
    count = max(1, int(settings.columns))
    ref_width = max(10, int(settings.column_width))
    ref_gutter = max(0, int(settings.gutter))
    ref_pitch = max(10, ref_width + ref_gutter)
    fallbacks: list[str] = []

    start_y = _merge_start_y(primary.start_y, secondary.start_y, height, max(1, int(primary.character_height)))
    bottom_y = int(primary.bottom_y)
    if abs(int(primary.bottom_y) - int(secondary.bottom_y)) <= max(30, round(height * 0.08)):
        bottom_y = round((int(primary.bottom_y) + int(secondary.bottom_y)) / 2)

    first_primary = int(primary.column_starts[0]) if primary.column_starts else int(primary.manual_x)
    first_secondary = int(secondary.column_starts[0]) if secondary.column_starts else int(secondary.manual_x)
    first_x, first_fallback = _choose_geometry_value(
        first_primary,
        first_secondary,
        int(settings.manual_x),
        scale=ref_pitch,
        pair_tolerance=0.05,
        reference_tolerance=0.12,
    )
    if first_fallback:
        fallbacks.append("manual_x")

    if ref_gutter > 0:
        gutter, gutter_fallback = _choose_geometry_value(
            int(primary.gutter),
            int(secondary.gutter),
            ref_gutter,
            scale=max(ref_gutter, round(ref_pitch * 0.10), 8),
            pair_tolerance=0.45,
            reference_tolerance=0.65,
        )
    else:
        gutter, gutter_fallback = max(0, int(primary.gutter)), False
    if gutter_fallback:
        fallbacks.append("gutter")

    column_width, width_fallback = _choose_geometry_value(
        int(primary.column_width),
        int(secondary.column_width),
        ref_width,
        scale=ref_width,
        pair_tolerance=0.08,
        reference_tolerance=0.22,
    )
    if width_fallback:
        fallbacks.append("column_width")

    p_starts = list(primary.column_starts)
    s_starts = list(secondary.column_starts)
    starts: list[int] = [first_x]
    for index in range(1, count):
        expected = first_x + index * ref_pitch
        p = int(p_starts[index]) if index < len(p_starts) else expected
        s = int(s_starts[index]) if index < len(s_starts) else expected
        chosen, used_ref = _choose_geometry_value(
            p,
            s,
            expected,
            scale=ref_pitch,
            pair_tolerance=0.05,
            reference_tolerance=0.12,
        )
        starts.append(chosen)
        if used_ref:
            fallbacks.append(f"column_start[{index}]")

    separator_scores: list[float] = []
    separator_centers: list[int] = []
    separator_mode = str(getattr(settings, "layout_column_separator_mode", "auto") or "auto").lower()
    if count > 1 and separator_mode == "present" and str(settings.layout_transform) == "identity":
        gray = np.asarray(ImageOps.grayscale(cleaned_source), dtype=np.uint8)
        ink = backend._analysis_ink_mask(gray, settings)
        body_top = max(0, min(height - 2, int(start_y)))
        body_bottom = max(body_top + 2, min(height, int(bottom_y or round(height * 0.97))))
        for index in range(count - 1):
            expected_center = first_x + index * ref_pitch + ref_width + ref_gutter / 2.0
            tracked = _separator_track(
                ink,
                expected_x=round(expected_center),
                pitch=ref_pitch,
                body_top=body_top,
                body_bottom=body_bottom,
            )
            if tracked is None:
                continue
            center, track_score = tracked
            separator_centers.append(center)
            separator_scores.append(track_score)

            divider = backend._detect_persistent_vertical_rule(
                ink,
                starts[index],
                min(width, starts[index] + ref_pitch),
                body_top,
                body_bottom,
                "present",
            )
            observed_gutter = None
            if divider is not None:
                candidate = int(divider.gutter_end - divider.gutter_start)
                if ref_gutter <= 0 or (0.55 * ref_gutter <= candidate <= 1.70 * ref_gutter):
                    observed_gutter = candidate
            effective_gutter = int(observed_gutter if observed_gutter is not None else gutter or ref_gutter)
            if ref_gutter > 0 and not (0.55 * ref_gutter <= effective_gutter <= 1.70 * ref_gutter):
                effective_gutter = ref_gutter
                if "gutter" not in fallbacks:
                    fallbacks.append("gutter")
            gutter = effective_gutter
            next_start = round(center + effective_gutter / 2.0)
            if index + 1 < len(starts):
                starts[index + 1] = next_start

            observed_width = round(center - effective_gutter / 2.0 - starts[index])
            if 0.78 * ref_width <= observed_width <= 1.22 * ref_width:
                column_width = observed_width
            elif "column_width" not in fallbacks:
                fallbacks.append("column_width")

    if ref_gutter > 0 and not (0.50 * ref_gutter <= gutter <= 1.80 * ref_gutter):
        gutter = ref_gutter
        if "gutter" not in fallbacks:
            fallbacks.append("gutter")
    for index in range(1, len(starts)):
        expected = first_x + index * ref_pitch
        if abs(starts[index] - expected) > ref_pitch * 0.16:
            starts[index] = expected
            marker = f"column_start[{index}]"
            if marker not in fallbacks:
                fallbacks.append(marker)

    char_height = max(1, int(primary.character_height))
    ref_char = max(1, int(settings.character_height))
    if not (0.50 * ref_char <= char_height <= 1.90 * ref_char):
        alt = max(1, int(secondary.character_height))
        char_height = alt if 0.50 * ref_char <= alt <= 1.90 * ref_char else ref_char
        fallbacks.append("character_height")

    box_score = min(1.0, max(0.15, float(primary.source_boxes) / 40.0))
    pair_scores = [
        _closeness(primary.manual_x, secondary.manual_x, ref_pitch * 0.12),
        _closeness(primary.column_width, secondary.column_width, ref_width * 0.22),
    ]
    if ref_gutter > 0:
        pair_scores.append(_closeness(primary.gutter, secondary.gutter, max(8, ref_gutter * 0.70)))
    consensus_score = float(np.mean(pair_scores)) if pair_scores else 0.5
    ref_scores = [
        _closeness(first_x, settings.manual_x, ref_pitch * 0.12),
        _closeness(column_width, ref_width, ref_width * 0.22),
    ]
    if ref_gutter > 0:
        ref_scores.append(_closeness(gutter, ref_gutter, max(8, ref_gutter * 0.70)))
    reference_score = float(np.mean(ref_scores)) if ref_scores else 0.5
    separator_score = float(np.mean(separator_scores)) if separator_scores else (0.25 if separator_mode == "present" else 0.60)
    confidence = max(0.0, min(1.0, 0.20 * box_score + 0.30 * consensus_score + 0.30 * reference_score + 0.20 * separator_score))

    method_parts = ["reliable_fusion", str(primary.method), str(secondary.method)]
    if separator_centers:
        method_parts.append("separator_anchor")
    if fallbacks:
        method_parts.append("fallback=" + ",".join(dict.fromkeys(fallbacks)))

    rights: list[int] = []
    p_rights = list(primary.column_rights)
    for index, start in enumerate(starts):
        observed = int(p_rights[index]) if index < len(p_rights) else start + column_width
        if observed <= start or observed - start > max(column_width * 1.45, ref_pitch * 1.2):
            observed = start + column_width
        rights.append(min(width, max(start + 1, observed)))

    return replace(
        primary,
        columns=count,
        start_y=start_y,
        bottom_y=max(start_y + 1, bottom_y),
        manual_x=first_x,
        column_width=max(10, int(column_width)),
        gutter=max(0, int(gutter)),
        character_height=char_height,
        row_padding=max(1, int(primary.row_padding)),
        method="+".join(method_parts),
        separator_x=(round(float(np.median(separator_centers))) if separator_centers else primary.separator_x),
        confidence=confidence,
        canonical_width=int(width),
        column_starts=tuple(int(x) for x in starts),
        column_rights=tuple(int(x) for x in rights),
    )


def _fuse_detected_geometry(primary: Any, secondary: Any, image_size: tuple[int, int]) -> Any:
    """Soft consensus for projects where the number of columns is intentionally detected."""
    width, height = image_size
    if int(primary.columns) != int(secondary.columns):
        return replace(
            primary,
            confidence=min(0.45, max(0.15, float(primary.source_boxes) / 80.0)),
            method=f"reliable_fusion+column_disagreement+{primary.method}+{secondary.method}",
        )
    char_height = max(1, int(primary.character_height))
    start_y = _merge_start_y(primary.start_y, secondary.start_y, height, char_height)
    starts = list(primary.column_starts)
    if len(primary.column_starts) == len(secondary.column_starts) and starts:
        pitch = max(10, round(width / max(1, int(primary.columns))))
        for i, (a, b) in enumerate(zip(primary.column_starts, secondary.column_starts)):
            if abs(int(a) - int(b)) <= pitch * 0.08:
                starts[i] = round((int(a) + int(b)) / 2)
    scores = [
        _closeness(primary.manual_x, secondary.manual_x, max(20, width * 0.05)),
        _closeness(primary.column_width, secondary.column_width, max(30, width * 0.08)),
    ]
    if max(primary.gutter, secondary.gutter) > 0:
        scores.append(_closeness(primary.gutter, secondary.gutter, max(12, width * 0.04)))
    confidence = max(0.15, min(1.0, 0.45 * min(1.0, float(primary.source_boxes) / 40.0) + 0.55 * float(np.mean(scores))))
    return replace(
        primary,
        start_y=start_y,
        manual_x=(int(starts[0]) if starts else int(primary.manual_x)),
        column_starts=tuple(int(x) for x in starts) if starts else primary.column_starts,
        confidence=confidence,
        method=f"reliable_fusion+{primary.method}+{secondary.method}",
    )


def detect_layout_parameters_reliable(image: Image.Image, settings: AppSettings, backend: Any) -> Any:
    """Noise-robust, cross-checked replacement for detect_layout_parameters."""
    source = normalize_page_rgb(image)
    if str(getattr(settings, "layout_transform", "identity") or "identity") != "identity":
        return backend._legacy_detect_layout_parameters(source, settings)

    cleaned = clean_layout_speckles(source, settings, backend)
    paddle_error: Exception | None = None
    projection_error: Exception | None = None
    primary = None
    secondary = None
    try:
        primary = _paddle_estimate(cleaned, settings, backend)
    except Exception as exc:
        paddle_error = exc
    try:
        secondary = _projection_estimate(cleaned, settings, backend)
    except Exception as exc:
        projection_error = exc

    if primary is None and secondary is None:
        raise RuntimeError(
            f"PaddleOCR 整页版面检测失败：{paddle_error}\n"
            f"投影版面检测也失败：{projection_error}"
        )
    if primary is None:
        secondary.confidence = min(0.70, max(0.30, float(secondary.source_boxes) / 8.0))
        secondary.method = f"reliable_fusion+projection_only+paddle_error={type(paddle_error).__name__ if paddle_error else 'unknown'}"
        return secondary
    if secondary is None:
        primary.confidence = min(0.70, max(0.25, float(primary.source_boxes) / 50.0))
        primary.method = f"reliable_fusion+paddle_only+projection_error={type(projection_error).__name__ if projection_error else 'unknown'}"
        return primary

    if str(getattr(settings, "layout_columns_policy", "detect") or "detect").lower() == "fixed":
        return _fuse_fixed_geometry(primary, secondary, settings, cleaned, backend)
    return _fuse_detected_geometry(primary, secondary, cleaned.size)
