"""Canonical local OCR recovery of oversized CJK heads and separator refinement.

Full chain from crop-local OCR re-detection to image-first recovery, safe raw
box duplicate suppression, and coarse/adaptive/first-content line placement.

The original heavy OCR core supplies its patchable callables, typed policies
and verified recovery codes at call time without a circular import, global
injection or changes to cached raw OCR observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math
import re
import unicodedata

import numpy as np
from PIL import Image, ImageOps

from ..models import AppSettings
from ..profile.dictionary import DictionaryProfile
from .headword_models import OCRRecord


@dataclass(frozen=True)
class CjkRecoveryDeps:
    """Live original OCR public/private callable operations and verification policy."""
    _robust_record_line_height: object
    _single_cjk_from_local_records: object
    _recover_oversized_cjk_ocr_records: object
    _record_already_represents_oversized_run: object
    _recover_image_first_oversized_cjk_records: object
    _suppress_raw_records_shadowed_by_verified_cjk_recovery: object
    refine_separator_y: object
    refine_separator_y_adaptive: object
    refine_first_content_y: object
    parse_headword_text: object
    _is_single_cjk_ideograph: object
    _leading_cjk_ideograph: object
    _is_chinese_ocr: object
    _header_cutoff: object
    _cjk_visual_projection_runs: object
    get_paddle_engine: object
    run_paddle_band: object
    _separator_analysis_x_bounds: object
    _otsu_threshold: object
    _true_runs: object
    normalize_page_rgb: object
    _VERIFIED_OVERSIZED_CJK_RECOVERIES: object


def _robust_record_line_height(
    deps: CjkRecoveryDeps, 
    records: list[OCRRecord],
    settings: AppSettings,
) -> float:
    """Estimate ordinary OCR-line height while ignoring giant merged boxes."""
    heights = sorted(
        max(1, int(record.box[3]) - int(record.box[1]))
        for record in records
        if record.text
    )
    if not heights:
        return max(8.0, float(settings.character_height))
    keep = max(1, int(math.ceil(len(heights) * 0.80)))
    sample = heights[:keep]
    return max(
        8.0,
        float(np.median(np.asarray(sample, dtype=float))),
    )


def _single_cjk_from_local_records(
    deps: CjkRecoveryDeps, 
    records: list[OCRRecord],
    settings: AppSettings,
    profile: DictionaryProfile,
    *,
    max_left_x: int | None = None,
) -> tuple[str, float, str]:
    """Return the best single-Han head from a tightly cropped local OCR pass."""
    parse_headword_text = deps.parse_headword_text
    _is_single_cjk_ideograph = deps._is_single_cjk_ideograph
    _leading_cjk_ideograph = deps._leading_cjk_ideograph
    ranked: list[tuple[int, int, float, str, str]] = []
    for record in records:
        if max_left_x is not None and int(record.box[0]) > int(max_left_x):
            continue
        text = str(record.text or "").strip()
        if not text:
            continue
        parsed = parse_headword_text(text, settings, profile=profile)
        if parsed is not None and _is_single_cjk_ideograph(parsed.normalized):
            word = parsed.normalized
            quality = 0
        else:
            word = _leading_cjk_ideograph(text)
            quality = 1
        if not word:
            continue
        ranked.append((
            quality,
            max(0, int(record.box[0])),
            -float(record.confidence),
            word,
            text,
        ))
    if not ranked:
        return "", 0.0, ""
    ranked.sort()
    _quality, _x0, neg_conf, word, source_text = ranked[0]
    return word, max(0.0, -neg_conf), source_text


def _recover_oversized_cjk_ocr_records(
    deps: CjkRecoveryDeps, 
    records: list[OCRRecord],
    band: Image.Image,
    settings: AppSettings,
    profile: DictionaryProfile,
    *,
    engine: Any | None = None,
    pixel_scale: float = 1.0,
) -> tuple[list[OCRRecord], list[dict[str, Any]]]:
    """Split one pathological multi-entry OCR box into physical CJK heads.

    This path is intentionally narrow. It runs only when a left-edge OCR box is
    far taller than normal text *and* the page pixels show at least two separate
    oversized-glyph runs inside that same box. Each physical run then receives
    a small local Paddle pass, so a head entirely omitted from the giant-box
    transcription can still be recovered.
    """
    _robust_record_line_height = deps._robust_record_line_height
    _single_cjk_from_local_records = deps._single_cjk_from_local_records
    _is_single_cjk_ideograph = deps._is_single_cjk_ideograph
    _is_chinese_ocr = deps._is_chinese_ocr
    _header_cutoff = deps._header_cutoff
    _cjk_visual_projection_runs = deps._cjk_visual_projection_runs
    get_paddle_engine = deps.get_paddle_engine
    run_paddle_band = deps.run_paddle_band
    normalize_page_rgb = deps.normalize_page_rgb
    if (
        not records
        or not _is_chinese_ocr(settings)
        or str(
            getattr(settings, "layout_writing_mode", "horizontal-tb")
        ).startswith("vertical")
    ):
        return list(records), []

    parser_controls = int(
        getattr(settings, "profile_parser_controls_version", 0) or 0
    ) >= 1
    if parser_controls and not bool(
        getattr(settings, "profile_cjk_allow_single_headword", True)
    ):
        return list(records), []

    gray = np.asarray(ImageOps.grayscale(band), dtype=np.uint8)
    scale = max(0.01, float(pixel_scale))
    header_cutoff = _header_cutoff(gray, settings, scale)
    zone_width, visual_runs = _cjk_visual_projection_runs(
        gray, header_cutoff, settings, scale
    )
    if len(visual_runs) < 2 or zone_width <= 0:
        return list(records), []

    normal_height = _robust_record_line_height(records, settings)
    giant_height_floor = max(
        normal_height * 2.8,
        float(settings.character_height) * 2.5,
    )
    output = list(records)
    details: list[dict[str, Any]] = []

    for parent in list(records):
        x0, y0, _x1, y1 = (int(value) for value in parent.box)
        parent_height = max(1, y1 - y0)
        if x0 > zone_width * 1.25 or parent_height < giant_height_floor:
            continue

        runs = [
            run for run in visual_runs
            if max(
                0,
                min(y1, run[1]) - max(y0, run[0]),
            ) >= max(1, run[1] - run[0]) * 0.55
        ]
        if len(runs) < 2:
            continue

        local_engine = engine
        if local_engine is None:
            try:
                local_engine = get_paddle_engine(settings)
            except Exception:
                local_engine = None

        parent_chars = [
            ch for ch in str(parent.text or "")
            if _is_single_cjk_ideograph(ch)
        ]
        exact_parent_fallback = (
            parent_chars if len(parent_chars) == len(runs) else []
        )

        recovered: list[OCRRecord] = []
        run_debug: list[dict[str, Any]] = []
        for run_index, (run_start, run_end) in enumerate(runs):
            run_height = max(1, int(run_end) - int(run_start))
            pad_y = max(6, round(run_height * 0.12))
            crop_top = max(0, int(run_start) - pad_y)
            crop_bottom = min(band.height, int(run_end) + pad_y)
            crop_right = min(
                band.width,
                max(
                    zone_width * 2,
                    round(run_height * 2.2),
                    zone_width + round(run_height * 1.25),
                ),
            )
            word = ""
            confidence = 0.0
            source_text = ""
            local_records: list[OCRRecord] = []
            if (
                local_engine is not None
                and crop_bottom > crop_top
                and crop_right >= 24
            ):
                try:
                    local_crop = normalize_page_rgb(band).crop(
                        (0, crop_top, crop_right, crop_bottom)
                    )
                    local_records = run_paddle_band(
                        local_crop, settings, engine=local_engine
                    )
                    word, confidence, source_text = (
                        _single_cjk_from_local_records(
                            local_records,
                            settings,
                            profile,
                            max_left_x=max(
                                12, round(zone_width * 1.15)
                            ),
                        )
                    )
                except Exception:
                    local_records = []

            if not word and exact_parent_fallback:
                word = exact_parent_fallback[run_index]
                confidence = float(parent.confidence)
                source_text = str(parent.text or "")

            if not word:
                run_debug.append({
                    "run": [int(run_start), int(run_end)],
                    "status": "local_ocr_no_single_cjk",
                    "local_texts": [
                        str(record.text) for record in local_records
                    ],
                })
                continue

            synthetic_right = min(
                band.width,
                max(zone_width, round(run_height * 1.10)),
            )
            recovered_confidence = (
                float(confidence)
                if local_records
                else float(parent.confidence)
            )
            recovered.append(OCRRecord(
                text=word,
                confidence=max(0.0, min(1.0, recovered_confidence)),
                box=(
                    max(0, min(x0, round(zone_width * 0.15))),
                    int(run_start),
                    max(1, int(synthetic_right)),
                    int(run_end),
                ),
                recovery="oversized_multi_entry_local_ocr",
                recovery_source_text=source_text,
                parent_box=tuple(int(v) for v in parent.box),
            ))
            run_debug.append({
                "run": [int(run_start), int(run_end)],
                "status": "recovered",
                "word": word,
                "local_text": source_text,
                "confidence": round(
                    max(0.0, min(1.0, recovered_confidence)), 6
                ),
            })

        fully_recovered = len(recovered) == len(runs)
        details.append({
            "parent_box": [int(v) for v in parent.box],
            "parent_text": str(parent.text or ""),
            "parent_height": int(parent_height),
            "normal_line_height": round(float(normal_height), 3),
            "visual_run_count": len(runs),
            "recovered_count": len(recovered),
            "applied": bool(fully_recovered),
            "runs": run_debug,
        })
        # Do not partially replace a giant box. Losing one physical head is
        # worse than retaining the original imperfect record; a future forced
        # refresh/local OCR pass may recover all runs.
        if not fully_recovered:
            continue

        output = [record for record in output if record is not parent]
        output.extend(recovered)

    output.sort(key=lambda item: (item.box[1], item.box[0]))
    return output, details
def _record_already_represents_oversized_run(
    deps: CjkRecoveryDeps, 
    record: OCRRecord,
    run: tuple[int, int],
    zone_width: int,
    settings: AppSettings,
    profile: DictionaryProfile,
) -> bool:
    """Return True when an existing OCR row already represents this visual run.

    Giant or multi-line boxes are deliberately excluded because they are the
    failure mode the image-first channel is intended to bypass.
    """
    parse_headword_text = deps.parse_headword_text
    _is_single_cjk_ideograph = deps._is_single_cjk_ideograph
    _VERIFIED_OVERSIZED_CJK_RECOVERIES = deps._VERIFIED_OVERSIZED_CJK_RECOVERIES
    x0, y0, _x1, y1 = (int(value) for value in record.box)
    run_start, run_end = (int(run[0]), int(run[1]))
    run_height = max(1, run_end - run_start)
    record_height = max(1, y1 - y0)
    if x0 > zone_width * 1.25 or record_height > run_height * 1.85:
        return False
    overlap = max(0, min(y1, run_end) - max(y0, run_start))
    center_delta = abs(
        ((y0 + y1) / 2.0) - ((run_start + run_end) / 2.0)
    )
    if overlap < run_height * 0.30 and center_delta > run_height * 0.45:
        return False
    if str(record.recovery or "") in _VERIFIED_OVERSIZED_CJK_RECOVERIES:
        return True
    parsed = parse_headword_text(record.text, settings, profile=profile)
    return bool(parsed and _is_single_cjk_ideograph(parsed.normalized))


def _recover_image_first_oversized_cjk_records(
    deps: CjkRecoveryDeps, 
    records: list[OCRRecord],
    band: Image.Image,
    settings: AppSettings,
    profile: DictionaryProfile,
    *,
    engine: Any | None = None,
    pixel_scale: float = 1.0,
) -> tuple[list[OCRRecord], list[dict[str, Any]]]:
    """Recover large CJK heads from page pixels even when OCR has no good box.

    Image geometry only discovers possible oversized runs. Each unmatched run
    receives a tight local Paddle pass and is promoted only when that crop
    resolves to one leading Han headword. Decorative Latin initials therefore
    remain rejected while clipped, omitted, or out-of-parent-box CJK heads can
    become ordinary downstream candidates.
    """
    _single_cjk_from_local_records = deps._single_cjk_from_local_records
    _record_already_represents_oversized_run = deps._record_already_represents_oversized_run
    _is_chinese_ocr = deps._is_chinese_ocr
    _header_cutoff = deps._header_cutoff
    _cjk_visual_projection_runs = deps._cjk_visual_projection_runs
    get_paddle_engine = deps.get_paddle_engine
    run_paddle_band = deps.run_paddle_band
    normalize_page_rgb = deps.normalize_page_rgb
    if (
        not _is_chinese_ocr(settings)
        or str(
            getattr(settings, "layout_writing_mode", "horizontal-tb")
        ).startswith("vertical")
        or not (
            getattr(profile, "family", "") == "cjk_visual"
            or getattr(profile, "key", "") == "cjk_visual"
        )
    ):
        return list(records), []

    parser_controls = int(
        getattr(settings, "profile_parser_controls_version", 0) or 0
    ) >= 1
    if parser_controls and not bool(
        getattr(settings, "profile_cjk_allow_single_headword", True)
    ):
        return list(records), []

    gray = np.asarray(ImageOps.grayscale(band), dtype=np.uint8)
    scale = max(0.01, float(pixel_scale))
    header_cutoff = _header_cutoff(gray, settings, scale)
    zone_width, visual_runs = _cjk_visual_projection_runs(
        gray,
        header_cutoff,
        settings,
        scale,
        relaxed=True,
    )
    if not visual_runs or zone_width <= 0:
        return list(records), []

    local_engine = engine
    if local_engine is None:
        try:
            local_engine = get_paddle_engine(settings)
        except Exception:
            local_engine = None
    if local_engine is None:
        return list(records), [{
            "mode": "image_first_oversized_run_rescue",
            "applied": False,
            "reason": "local_ocr_unavailable",
            "visual_run_count": len(visual_runs),
        }]

    rgb_band = normalize_page_rgb(band)
    output = list(records)
    details: list[dict[str, Any]] = []
    for run_start, run_end in visual_runs[:32]:
        run = (int(run_start), int(run_end))
        if any(
            _record_already_represents_oversized_run(
                record,
                run,
                zone_width,
                settings,
                profile,
            )
            for record in output
        ):
            details.append({
                "mode": "image_first_oversized_run_rescue",
                "run": [int(run_start), int(run_end)],
                "status": "already_represented",
                "applied": False,
            })
            continue

        run_height = max(1, int(run_end) - int(run_start))
        pad_y = max(6, round(run_height * 0.14))
        crop_top = max(0, int(run_start) - pad_y)
        crop_bottom = min(band.height, int(run_end) + pad_y)
        crop_right = min(
            band.width,
            max(
                zone_width * 2,
                round(run_height * 2.25),
                zone_width + round(run_height * 1.35),
            ),
        )
        local_records: list[OCRRecord] = []
        word = ""
        confidence = 0.0
        source_text = ""
        try:
            if crop_bottom > crop_top and crop_right >= 24:
                local_crop = rgb_band.crop(
                    (0, crop_top, crop_right, crop_bottom)
                )
                local_records = run_paddle_band(
                    local_crop,
                    settings,
                    engine=local_engine,
                )
                word, confidence, source_text = _single_cjk_from_local_records(
                    local_records,
                    settings,
                    profile,
                    max_left_x=max(12, round(zone_width * 1.20)),
                )
        except Exception:
            local_records = []

        if not word:
            details.append({
                "mode": "image_first_oversized_run_rescue",
                "run": [int(run_start), int(run_end)],
                "status": "local_ocr_no_single_cjk",
                "applied": False,
                "local_texts": [
                    str(record.text) for record in local_records
                ],
            })
            continue

        synthetic_right = min(
            band.width,
            max(zone_width, round(run_height * 1.10)),
        )
        candidate = OCRRecord(
            text=word,
            confidence=max(0.0, min(1.0, float(confidence))),
            box=(
                0,
                int(run_start),
                max(1, int(synthetic_right)),
                int(run_end),
            ),
            recovery="image_first_oversized_local_ocr",
            recovery_source_text=source_text,
            parent_box=None,
        )
        output.append(candidate)
        details.append({
            "mode": "image_first_oversized_run_rescue",
            "run": [int(run_start), int(run_end)],
            "status": "recovered",
            "applied": True,
            "word": word,
            "local_text": source_text,
            "confidence": round(float(candidate.confidence), 6),
        })

    output.sort(key=lambda item: (item.box[1], item.box[0]))
    return output, details


def _suppress_raw_records_shadowed_by_verified_cjk_recovery(
    deps: CjkRecoveryDeps, 
    records: list[OCRRecord],
) -> tuple[list[OCRRecord], list[dict[str, Any]]]:
    """Drop raw OCR boxes that duplicate verified CJK recovery rows.

    Image-first recovery adds a synthetic single-Han record while preserving the
    immutable raw Paddle cache. Without derived-record dedup, that synthetic row
    can be merged back with its own source box, for example 摆 plus 摆1, or with
    a giant raw box spanning several recovered heads. Suppression affects only
    the effective derived record list; the raw cache remains untouched.
    """
    _leading_cjk_ideograph = deps._leading_cjk_ideograph
    _VERIFIED_OVERSIZED_CJK_RECOVERIES = deps._VERIFIED_OVERSIZED_CJK_RECOVERIES
    verified = [
        record for record in records
        if str(record.recovery or "") in _VERIFIED_OVERSIZED_CJK_RECOVERIES
    ]
    if not verified:
        return list(records), []

    def _norm(text: str) -> str:
        return re.sub(
            r"\s+",
            "",
            unicodedata.normalize("NFKC", str(text or "")),
        )

    output: list[OCRRecord] = []
    details: list[dict[str, Any]] = []
    for record in records:
        if str(record.recovery or ""):
            output.append(record)
            continue

        raw_text = _norm(record.text)
        rx0, ry0, rx1, ry1 = (int(value) for value in record.box)
        raw_height = max(1, ry1 - ry0)
        suppressor: OCRRecord | None = None
        reason = ""

        for recovered in verified:
            sx0, sy0, sx1, sy1 = (int(value) for value in recovered.box)
            recovered_height = max(1, sy1 - sy0)
            vertical_overlap = max(0, min(ry1, sy1) - max(ry0, sy0))
            horizontal_overlap = max(0, min(rx1, sx1) - max(rx0, sx0))
            if (
                vertical_overlap < recovered_height * 0.45
                or horizontal_overlap <= 0
            ):
                continue

            source_text = _norm(recovered.recovery_source_text)
            recovered_text = _norm(recovered.text)
            if source_text and raw_text == source_text:
                suppressor = recovered
                reason = "same_recovery_source_text"
                break

            # Conservative fallback for engines that normalize away a sense
            # suffix locally. Require the same leading Han plus a clearly taller
            # raw box so ordinary neighboring OCR fragments are not removed.
            raw_leading = _leading_cjk_ideograph(record.text)
            if (
                raw_leading
                and recovered_text == raw_leading
                and raw_height >= recovered_height * 1.20
            ):
                suppressor = recovered
                reason = "same_leading_han_taller_raw_box"
                break

        if suppressor is None:
            output.append(record)
            continue

        details.append({
            "mode": "verified_cjk_recovery_duplicate_suppression",
            "applied": True,
            "status": "suppressed_raw_record",
            "reason": reason,
            "raw_text": str(record.text or ""),
            "raw_box": [int(v) for v in record.box],
            "recovered_word": str(suppressor.text or ""),
            "recovery_source_text": str(
                suppressor.recovery_source_text or ""
            ),
            "recovered_box": [int(v) for v in suppressor.box],
            "recovery": str(suppressor.recovery or ""),
        })

    output.sort(key=lambda item: (item.box[1], item.box[0]))
    return output, details


def refine_separator_y(
    deps: CjkRecoveryDeps, 
    gray: np.ndarray,
    coarse_y: int,
    line_height: int,
    settings: AppSettings,
    pixel_scale: float = 1.0,
    lower_bound: int = 0,
) -> tuple[int, dict[str, Any]]:
    """Refine a coarse headword marker using a local horizontal ink valley.

    ``coarse_y`` is the OCR-derived marker position in the straightened column
    band.  Around it we inspect each row's black-pixel proportion.  A small
    vertical safety band is averaged so a one-pixel hole inside a descender is
    not mistaken for inter-line whitespace.  The returned Y is the centre of
    the contiguous near-minimum valley that contains the global minimum.

    This intentionally remains a *local* correction: OCR decides which text
    line is the headword, while projection only nudges the marker to the safest
    whitespace between the preceding line and the current one.
    """
    _separator_analysis_x_bounds = deps._separator_analysis_x_bounds
    _otsu_threshold = deps._otsu_threshold
    _true_runs = deps._true_runs
    if not settings.paddle_refine_separator_y or gray.size == 0:
        return int(coarse_y), {"enabled": False, "reason": "disabled"}

    height, width = gray.shape[:2]
    if height <= 2 or width <= 8:
        return int(coarse_y), {"enabled": True, "reason": "image_too_small"}

    coarse_y = int(min(height - 1, max(lower_bound, coarse_y)))
    line_height = max(2, int(line_height))
    search_ratio = max(0.05, min(0.80, float(settings.paddle_separator_search_ratio)))
    search_radius = max(2, round(line_height * search_ratio))
    top = max(int(lower_bound), coarse_y - search_radius)
    bottom = min(height - 1, coarse_y + search_radius)
    if bottom <= top:
        return coarse_y, {"enabled": True, "reason": "empty_search"}

    x0, x1 = _separator_analysis_x_bounds(width, settings, pixel_scale)

    roi = gray[top:bottom + 1, x0:x1]
    threshold = _otsu_threshold(roi)
    ink = roi <= threshold

    # Remove page borders / vertical rules that remain dark through almost the
    # whole local search window. They add a constant term to every row and can
    # flatten the whitespace valley.
    if ink.shape[0] >= 3 and ink.shape[1] >= 3:
        rule_columns = ink.mean(axis=0) >= 0.72
        if rule_columns.any():
            ink = ink.copy()
            ink[:, rule_columns] = False

    row_ink = ink.mean(axis=1).astype(np.float64)
    band_radius = max(0, round(max(0, settings.paddle_separator_band_radius) * pixel_scale))
    band_radius = min(band_radius, max(0, (len(row_ink) - 1) // 3))
    if band_radius > 0:
        kernel = np.ones(2 * band_radius + 1, dtype=np.float64) / (2 * band_radius + 1)
        padded = np.pad(row_ink, (band_radius, band_radius), mode="edge")
        smooth = np.convolve(padded, kernel, mode="valid")
    else:
        smooth = row_ink.copy()

    minimum_index = int(np.argmin(smooth))
    minimum = float(smooth[minimum_index])
    # Expand around the minimum through rows that are effectively part of the
    # same whitespace valley. The tolerance scales to both image width and the
    # local distribution, so near-white plateaus are centred rather than pinned
    # to whichever scan row happened to contain zero pixels.
    q35 = float(np.percentile(smooth, 35)) if smooth.size else minimum
    quantization = 1.0 / max(1, ink.shape[1] * max(1, 2 * band_radius + 1))
    valley_tolerance = max(quantization, (q35 - minimum) * 0.35)
    low_rows = smooth <= (minimum + valley_tolerance)
    runs = _true_runs(low_rows)
    valley = next(
        ((start, end) for start, end in runs if start <= minimum_index < end),
        (minimum_index, minimum_index + 1),
    )
    valley_center = round((valley[0] + valley[1] - 1) / 2)

    # A low-ink run that reaches the edge of our search interval is not a
    # bounded inter-line gap.  The common case is the first printed line of a
    # page/column: there may be a large blank area above it, and centring that
    # open whitespace would drag the separator far upward.  In that situation
    # keep the OCR coarse marker instead of inventing a new Y from an unbounded
    # valley.
    # Only an upper-edge-open valley is dangerous for separator placement.
    # The genuine gap immediately above a tightly packed headword can extend
    # to the *bottom* of a small search interval, so bottom contact alone must
    # not suppress a useful downward correction.
    valley_touches_search_edge = valley[0] == 0
    if valley_touches_search_edge:
        refined_y = int(coarse_y)
        refinement_reason = "open_valley_at_search_edge_keep_coarse"
    else:
        refined_y = int(top + valley_center)
        refinement_reason = "bounded_low_ink_valley"

    return refined_y, {
        "enabled": True,
        "reason": refinement_reason,
        "coarse_y": coarse_y,
        "refined_y": refined_y,
        "shift": refined_y - coarse_y,
        "search_top": top,
        "search_bottom": bottom,
        "search_radius": search_radius,
        "line_height": line_height,
        "band_radius": band_radius,
        "threshold": threshold,
        "minimum_ink_ratio": round(minimum, 6),
        "coarse_ink_ratio": round(float(smooth[min(len(smooth) - 1, max(0, coarse_y - top))]), 6),
        "valley_start": int(top + valley[0]),
        "valley_end": int(top + valley[1] - 1),
        "valley_touches_search_edge": valley_touches_search_edge,
        "analysis_x0": x0,
        "analysis_x1": x1,
    }


def refine_separator_y_adaptive(
    deps: CjkRecoveryDeps, 
    gray: np.ndarray,
    coarse_y: int,
    reference_line_height: int,
    settings: AppSettings,
    pixel_scale: float = 1.0,
    lower_bound: int = 0,
    content_top: int | None = None,
    preceding_gap_hint: int | None = None,
    fallback_refiner: Any | None = None,
) -> tuple[int, dict[str, Any]]:
    """Trace the nearest blank band above a CJK entry.

    ``preceding_gap_hint`` remains for compatibility/diagnostics. When dense
    print has no stable blank run, ``fallback_refiner`` selects the local-valley
    fallback without changing the adaptive geometry policy.
    """
    refine_separator_y = deps.refine_separator_y
    _separator_analysis_x_bounds = deps._separator_analysis_x_bounds
    _otsu_threshold = deps._otsu_threshold
    _true_runs = deps._true_runs
    if not settings.paddle_refine_separator_y or gray.size == 0:
        return int(coarse_y), {"enabled": False, "reason": "disabled", "adaptive_mode": "off"}
    height, width = gray.shape[:2]
    if height <= 2 or width <= 8:
        return int(coarse_y), {"enabled": True, "reason": "image_too_small", "adaptive_mode": "fallback"}

    line_h = max(3, int(round(reference_line_height)))
    coarse_y = int(min(height - 1, max(lower_bound, coarse_y)))
    if content_top is None:
        runtime_width = max(1, int(gray.shape[1]))
        row_padding = int(settings.row_padding)
        content_top = coarse_y + max(0, row_padding)
    content_top = int(min(height - 1, max(lower_bound, content_top)))

    # Analyse enough of the column to see the preceding blank band and a small
    # portion of the current entry.  The logic remains local to the candidate.
    look_up = max(8, round(line_h * 1.30))
    # Look far enough below OCR box.y to recover when the box accidentally
    # starts inside the preceding text line.  The actual headword can begin
    # after one full inter-line gap, so half a line was insufficient.
    look_down = max(7, round(line_h * 1.10))
    top = max(int(lower_bound), content_top - look_up)
    bottom = min(height - 1, content_top + look_down)
    if bottom <= top:
        return coarse_y, {"enabled": True, "reason": "empty_search", "adaptive_mode": "fallback"}

    x0, x1 = _separator_analysis_x_bounds(width, settings, pixel_scale)
    roi = gray[top:bottom + 1, x0:x1]
    threshold = _otsu_threshold(roi)
    ink = roi <= threshold

    # A page border / column rule can be black on every row and would make an
    # otherwise empty separator band look non-blank. Remove such rule columns.
    if ink.shape[0] >= 3 and ink.shape[1] >= 3:
        rule_columns = ink.mean(axis=0) >= 0.72
        if rule_columns.any():
            # Remove only *narrow* persistent dark runs. A broad text block can
            # occupy the same X range on several neighbouring lines and must not
            # be mistaken for a vertical page rule.
            narrow_rule = np.zeros_like(rule_columns, dtype=bool)
            max_rule_width = max(2, round(ink.shape[1] * 0.025))
            for a, b in _true_runs(rule_columns):
                if b - a <= max_rule_width:
                    narrow_rule[a:b] = True
            if narrow_rule.any():
                ink = ink.copy()
                ink[:, narrow_rule] = False

    row_ink = ink.mean(axis=1).astype(np.float64)
    if row_ink.size >= 3:
        padded = np.pad(row_ink, (1, 1), mode="edge")
        smooth = np.convolve(padded, np.ones(3, dtype=np.float64) / 3.0, mode="valid")
    else:
        smooth = row_ink.copy()

    # "Blank" is intentionally tolerant rather than exactly zero: old scans
    # contain dust, antialiasing and residual punctuation.  Conversely, an ink
    # onset must be sustained for several rows so a single speck does not cause
    # us to reverse direction too early.
    quantization = 1.0 / max(1, ink.shape[1] * 3)
    positive = smooth[smooth > 0]
    low_positive = float(np.percentile(positive, 20)) if positive.size else 0.0
    blank_threshold = max(quantization * 2.5, min(0.010, low_positive * 0.45 if low_positive else 0.0025))
    blank_mask = smooth <= blank_threshold
    ink_threshold = max(blank_threshold * 1.8, quantization * 5.0)
    ink_mask = smooth > ink_threshold

    target_local = int(min(len(smooth) - 1, max(0, content_top - top)))
    min_ink_rows = max(2, round(line_h * 0.07))
    min_blank_rows = max(2, round(line_h * 0.08))
    # User-configurable safety clearance is a literal source-pixel distance.
    # A value of 0 is allowed when the user deliberately wants the rule to
    # touch the detected ink boundary.
    configured_safety = max(0, int(getattr(settings, "paddle_separator_safety_px", 2)))
    safety = max(0, round(configured_safety * max(0.5, float(pixel_scale))))

    # Step 1: establish an image-derived ink onset rather than blindly trusting
    # OCR box.y.  OCR can occasionally merge the preceding definition line into
    # the headword box, so a non-blank box top is not automatically the current
    # headword.  If box.y starts in ink, look a short distance downward for a
    # *real inter-line blank run* followed by sustained ink; when found, the ink
    # after that gap is the current headword.  This relocation uses a stricter
    # blank-run length than ordinary separator refinement so internal white holes
    # inside a large Han glyph are not mistaken for a line break.
    max_onset_local = min(len(smooth) - 1, target_local + max(6, round(line_h * 0.90)))
    onset_local: int | None = None
    relocated_from_prior_ink = False
    box_top_was_blank = bool(blank_mask[target_local])
    relocation_blank_rows = max(min_blank_rows, round(line_h * 0.14))

    if box_top_was_blank:
        i = target_local + 1
        while i <= max_onset_local:
            run_end = min(len(smooth), i + min_ink_rows)
            sustained_nonblank = (
                run_end - i >= min_ink_rows
                and bool(np.all(~blank_mask[i:run_end]))
            )
            if sustained_nonblank or bool(ink_mask[i]):
                onset_local = i
                break
            i += 1
    else:
        # First assume box.y is correct.  Only replace it when a sufficiently
        # long blank run appears soon below it and is followed by a new ink run.
        i = target_local + max(1, min_ink_rows)
        while i <= max_onset_local:
            if not bool(blank_mask[i]):
                i += 1
                continue
            gap_start = i
            while i <= max_onset_local and bool(blank_mask[i]):
                i += 1
            gap_end = i
            if gap_end - gap_start < relocation_blank_rows:
                continue
            j = gap_end
            while j <= max_onset_local:
                run_end = min(len(smooth), j + min_ink_rows)
                sustained_nonblank = (
                    run_end - j >= min_ink_rows
                    and bool(np.all(~blank_mask[j:run_end]))
                )
                if sustained_nonblank or bool(ink_mask[j]):
                    onset_local = j
                    relocated_from_prior_ink = True
                    break
                j += 1
            if onset_local is not None:
                break
        if onset_local is None:
            onset_local = target_local

    if onset_local is None:
        onset_local = target_local

    onset_y = top + onset_local
    anchor_y = int(min(height - 1, max(lower_bound, onset_y - safety)))

    # Step 2: reverse direction and find the nearest *consecutive* blank run
    # immediately above the current glyph.  We scan upward from the ink onset,
    # accumulate blank rows, and accept the first run reaching min_blank_rows.
    blank_run_end: int | None = None       # exclusive, nearest to the glyph
    blank_run_start: int | None = None
    j = onset_local - 1
    while j >= 0:
        if blank_mask[j]:
            run_end = j + 1
            k = j
            while k >= 0 and blank_mask[k]:
                k -= 1
            run_start = k + 1
            if run_end - run_start >= min_blank_rows:
                blank_run_start, blank_run_end = run_start, run_end
                break
            j = k
        else:
            j -= 1

    if blank_run_start is not None and blank_run_end is not None:
        # Use the bottom of the nearest valid blank band.  Keep ``safety`` rows
        # clear of the actual ink onset so the rule never cuts into the glyph.
        # This is equivalent to "nearest blank above the word, then stay ~2 px
        # above the ink" and is intentionally more downward-biased than v2.8.13.
        blank_bottom_y = top + blank_run_end - 1
        refined = min(blank_bottom_y, onset_y - safety)
        refined = int(min(height - 1, max(lower_bound, refined)))
        reason = "nearest_blank_band_above_headword"
        return refined, {
            "enabled": True,
            "reason": reason,
            "adaptive_mode": "local_blank_trace",
            "coarse_y": coarse_y,
            "refined_y": refined,
            "shift": refined - coarse_y,
            "reference_line_height": line_h,
            "content_top": content_top,
            "current_ink_onset": onset_y,
            "anchor_y": anchor_y,
            "box_top_was_blank": box_top_was_blank,
            "relocated_from_prior_ink": relocated_from_prior_ink,
            "relocation_blank_rows": int(relocation_blank_rows),
            "blank_run_start": int(top + blank_run_start),
            "blank_run_end": int(top + blank_run_end - 1),
            "blank_run_height": int(blank_run_end - blank_run_start),
            "minimum_blank_rows": int(min_blank_rows),
            "minimum_ink_rows": int(min_ink_rows),
            "safety_pixels": int(safety),
            "configured_safety_pixels": int(configured_safety),
            "blank_threshold": round(float(blank_threshold), 6),
            "ink_threshold": round(float(ink_threshold), 6),
            "threshold": threshold,
            "search_top": top,
            "search_bottom": bottom,
            "analysis_x0": x0,
            "analysis_x1": x1,
            "preceding_gap_hint": preceding_gap_hint,
        }

    # Extremely dense dictionaries can genuinely have no stable run of blank
    # rows. Preserve the local-valley fallback while allowing an explicit
    # compatibility refiner to own the final geometry adapter.
    refine_dense = fallback_refiner or refine_separator_y
    refined, legacy = refine_dense(
        gray, coarse_y, line_h, settings,
        pixel_scale=pixel_scale,
        lower_bound=lower_bound,
    )
    if legacy.get("reason") == "bounded_low_ink_valley" and legacy.get("valley_end") is not None:
        valley_end = int(legacy["valley_end"])
        refined = min(max(lower_bound, onset_y - safety), valley_end)
        legacy["refined_y"] = int(refined)
        legacy["shift"] = int(refined) - int(coarse_y)
        legacy["reason"] = "dense_valley_fallback_bottom_bias"
    legacy["adaptive_mode"] = "dense_fallback"
    legacy["current_ink_onset"] = int(onset_y)
    legacy["anchor_y"] = int(anchor_y)
    legacy["box_top_was_blank"] = bool(box_top_was_blank)
    legacy["relocated_from_prior_ink"] = bool(relocated_from_prior_ink)
    legacy["relocation_blank_rows"] = int(relocation_blank_rows)
    legacy["minimum_blank_rows"] = int(min_blank_rows)
    legacy["minimum_ink_rows"] = int(min_ink_rows)
    legacy["safety_pixels"] = int(safety)
    legacy["configured_safety_pixels"] = int(configured_safety)
    legacy["blank_threshold"] = round(float(blank_threshold), 6)
    legacy["ink_threshold"] = round(float(ink_threshold), 6)
    legacy["preceding_gap_hint"] = preceding_gap_hint
    return int(refined), legacy


def refine_first_content_y(
    deps: CjkRecoveryDeps, 
    gray: np.ndarray,
    coarse_y: int,
    line_height: int,
    settings: AppSettings,
    pixel_scale: float = 1.0,
    lower_bound: int = 0,
) -> tuple[int, dict[str, Any]]:
    """Place the first entry marker at the onset of the first sustained ink run.

    The first printed entry has no preceding text line, so an inter-line valley
    does not exist.  Using the normal valley algorithm either keeps a slightly
    inaccurate OCR top or, on older versions, could drift upward into the large
    blank margin.  For this special case we scan downward around the OCR top and
    choose the first Y at which printed ink persists for several consecutive
    rows.  This follows the user's requested "first continuous-ink Y" rule.
    """
    _separator_analysis_x_bounds = deps._separator_analysis_x_bounds
    _otsu_threshold = deps._otsu_threshold
    _true_runs = deps._true_runs
    if not settings.paddle_refine_separator_y or gray.size == 0:
        return int(coarse_y), {"enabled": False, "reason": "disabled"}
    height, width = gray.shape[:2]
    coarse_y = int(min(height - 1, max(lower_bound, coarse_y)))
    line_height = max(2, int(line_height))
    search_ratio = max(0.05, min(0.80, float(settings.paddle_separator_search_ratio)))
    radius = max(2, round(line_height * search_ratio))
    top = max(int(lower_bound), coarse_y - radius)
    # The coarse marker is normally OCR-top minus row padding, not the visual
    # centre of the glyphs. Give the downward side more room so the sustained
    # ink onset is fully visible even when OCR's box starts a few pixels early.
    bottom = min(height - 1, coarse_y + max(radius, line_height // 2))
    if bottom <= top:
        return coarse_y, {"enabled": True, "reason": "empty_search"}

    x0, x1 = _separator_analysis_x_bounds(width, settings, pixel_scale)
    roi = gray[top:bottom + 1, x0:x1]
    threshold = _otsu_threshold(roi)
    ink = roi <= threshold
    if ink.shape[0] >= 3 and ink.shape[1] >= 3:
        rule_columns = ink.mean(axis=0) >= 0.72
        if rule_columns.any():
            ink = ink.copy()
            ink[:, rule_columns] = False
    row_ink = ink.mean(axis=1).astype(np.float64)

    # A row is "ink-active" when it contains more than a few quantized dark
    # pixels. Requiring a short sustained run rejects isolated dust/antialiasing.
    quantization = 1.0 / max(1, ink.shape[1])
    positive = row_ink[row_ink > 0]
    local_low = float(np.percentile(positive, 20)) if positive.size else 0.0
    active_threshold = max(quantization * 3.0, min(0.004, local_low * 0.55 if local_low else 0.002))
    active = row_ink >= active_threshold
    min_run = max(2, round(max(1, settings.paddle_separator_band_radius) * pixel_scale) + 1)
    runs = [(a, b) for a, b in _true_runs(active) if (b - a) >= min_run]

    # Prefer the first sustained run whose centre is not implausibly far above
    # the OCR top. This still catches accents at the top of the headword line.
    onset = None
    coarse_local = coarse_y - top
    for start, end in runs:
        if end >= max(0, coarse_local - max(2, line_height // 3)):
            onset = start
            break
    if onset is None:
        refined = coarse_y
        reason = "no_sustained_ink_keep_coarse"
    else:
        ink_onset = int(top + onset)
        # A separator should mark the whitespace immediately *before* the first
        # entry, not touch the top stroke/accent of the glyph.  Keep a small
        # scale-aware clearance above the sustained-ink onset while respecting
        # the header/lower bound.
        clearance = max(
            2,
            round(
                max(1.0, line_height * 0.12)
                + max(0, settings.row_padding) * 0.35 * pixel_scale
            ),
        )
        refined = max(int(lower_bound), ink_onset - clearance)
        reason = "whitespace_before_first_sustained_ink"

    return refined, {
        "enabled": True,
        "reason": reason,
        "coarse_y": coarse_y,
        "refined_y": refined,
        "shift": refined - coarse_y,
        "search_top": top,
        "search_bottom": bottom,
        "line_height": line_height,
        "threshold": threshold,
        "active_ink_threshold": round(float(active_threshold), 6),
        "minimum_active_run": min_run,
        "analysis_x0": x0,
        "analysis_x1": x1,
    }

