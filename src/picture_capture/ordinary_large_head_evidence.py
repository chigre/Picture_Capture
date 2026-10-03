from __future__ import annotations

"""OCR-independent oversized headword evidence for universal ordinary drawing.

This detector is intentionally self-contained from the historical
``ordinary_cjk_large_heads`` recovery path. It uses only physical ink geometry
and never depends on indentation polarity, OCR text, or parser semantics.

A grouped physical region is not assumed to contain exactly one headword. Two
consecutive oversized heads can be joined by scan noise or fragment grouping;
when a reliable vertical ink valley separates two individually valid oversized
glyph regions, the detector emits two evidence events so Layout role fusion can
assign ``entry/body`` semantics to each head independently.
"""

from typing import Any

import numpy as np
from PIL import Image

from .models import AppSettings, Entry
from .ordinary_visual import _components, _otsu


def _uses_cjk_large_heads(settings: AppSettings) -> bool:
    """Keep oversized single-glyph evidence opt-in to CJK dictionary families."""
    if not bool(getattr(settings, "profile_cjk_allow_single_headword", True)):
        return False
    profile_id = str(getattr(settings, "dictionary_profile_id", "") or "").lower()
    ocr_language = str(getattr(settings, "ocr_language", "") or "").lower()
    paddle_language = str(getattr(settings, "paddle_language", "") or "").lower()
    return bool(
        "cjk" in profile_id
        or any(token in ocr_language for token in (
            "chi_sim", "chi_tra", "chinese", "han", "jpn", "jpn_vert",
        ))
        or paddle_language in {"ch", "chi_sim", "chi_tra", "chinese_cht", "japan"}
    )


def _overlap(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def _merge_box(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    return (
        min(left[0], right[0]),
        min(left[1], right[1]),
        max(left[2], right[2]),
        max(left[3], right[3]),
    )


def _fragment_neighbors(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
    line_height: float,
) -> bool:
    lw, lh = max(1, left[2] - left[0]), max(1, left[3] - left[1])
    rw, rh = max(1, right[2] - right[0]), max(1, right[3] - right[1])
    vertical_overlap = _overlap(left[1], left[3], right[1], right[3]) / float(max(1, min(lh, rh)))
    horizontal_overlap = _overlap(left[0], left[2], right[0], right[2]) / float(max(1, min(lw, rw)))
    horizontal_gap = max(0, max(left[0], right[0]) - min(left[2], right[2]))
    vertical_gap = max(0, max(left[1], right[1]) - min(left[3], right[3]))
    return bool(
        (vertical_overlap >= 0.30 and horizontal_gap <= line_height * 0.75)
        or (horizontal_overlap >= 0.24 and vertical_gap <= line_height * 0.50)
    )


def _large_fragments(
    ink: np.ndarray,
    line_height: float,
) -> list[tuple[int, int, int, int]]:
    minimum_area = max(3, round(line_height * line_height * 0.012))
    fragments: list[tuple[int, int, int, int]] = []
    for x0, y0, x1, y1, area in _components(ink):
        width = int(x1) - int(x0)
        height = int(y1) - int(y0)
        if int(area) < minimum_area:
            continue
        if width > line_height * 3.20 or height > line_height * 3.45:
            continue
        if height < line_height * 0.42:
            continue
        if not (
            height >= line_height * 1.10
            or (width >= line_height * 1.15 and height >= line_height * 0.62)
        ):
            continue
        fragments.append((int(x0), int(y0), int(x1), int(y1)))
    return fragments


def _group_fragments(
    fragments: list[tuple[int, int, int, int]],
    line_height: float,
) -> list[tuple[int, int, int, int]]:
    groups = list(fragments)
    changed = True
    while changed:
        changed = False
        output: list[tuple[int, int, int, int]] = []
        while groups:
            current = groups.pop(0)
            remaining: list[tuple[int, int, int, int]] = []
            for candidate in groups:
                if _fragment_neighbors(current, candidate, line_height):
                    current = _merge_box(current, candidate)
                    changed = True
                else:
                    remaining.append(candidate)
            groups = remaining
            output.append(current)
        groups = output
    return groups


def _trim_box_to_ink(
    ink: np.ndarray,
    box: tuple[int, int, int, int],
) -> tuple[int, int, int, int] | None:
    x0, y0, x1, y1 = box
    x0 = max(0, int(x0))
    y0 = max(0, int(y0))
    x1 = min(int(ink.shape[1]), int(x1))
    y1 = min(int(ink.shape[0]), int(y1))
    if x1 <= x0 or y1 <= y0:
        return None
    roi = np.asarray(ink[y0:y1, x0:x1], dtype=bool)
    ys, xs = np.nonzero(roi)
    if xs.size == 0 or ys.size == 0:
        return None
    return (
        x0 + int(xs.min()),
        y0 + int(ys.min()),
        x0 + int(xs.max()) + 1,
        y0 + int(ys.max()) + 1,
    )


def _valid_single_head_box(
    ink: np.ndarray,
    box: tuple[int, int, int, int],
    line_height: float,
    *,
    relaxed_height: bool = False,
) -> bool:
    x0, y0, x1, y1 = box
    width = int(x1) - int(x0)
    height = int(y1) - int(y0)
    minimum_height = line_height * (1.24 if relaxed_height else 1.38)
    if not (minimum_height <= height <= line_height * 3.45):
        return False
    if not (line_height * 0.68 <= width <= line_height * 3.80):
        return False
    aspect = height / float(max(1, width))
    if not 0.42 <= aspect <= 3.20:
        return False
    roi = ink[y0:y1, x0:x1]
    return bool(roi.size and float(roi.mean()) >= 0.025)


def _split_candidate_once(
    ink: np.ndarray,
    box: tuple[int, int, int, int],
    line_height: float,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None:
    """Split one suspiciously tall grouped region at a credible ink valley.

    The split is deliberately conservative: both resulting regions must remain
    individually valid oversized-head boxes. This prevents internal white bands
    inside one complex CJK glyph from creating a false second headword.
    """
    x0, y0, x1, y1 = box
    height = int(y1) - int(y0)
    if height < line_height * 2.45:
        return None

    roi = np.asarray(ink[y0:y1, x0:x1], dtype=np.uint8)
    if roi.ndim != 2 or roi.size == 0:
        return None
    row_ink = roi.sum(axis=1).astype(float)
    active_values = row_ink[row_ink > 0]
    if active_values.size == 0:
        return None

    smooth_radius = max(1, int(round(line_height * 0.035)))
    kernel = np.ones(2 * smooth_radius + 1, dtype=float)
    kernel /= float(kernel.size)
    smooth = np.convolve(row_ink, kernel, mode="same")
    typical = float(np.median(active_values))

    # A genuine pair needs enough room for two oversized glyphs. Keep the cut
    # away from both ends and prefer a valley reasonably near the middle rather
    # than an arbitrary internal white stroke of one glyph.
    minimum_segment = max(4, int(round(line_height * 1.12)))
    lo = minimum_segment
    hi = height - minimum_segment
    if hi <= lo:
        return None

    center = height / 2.0
    candidates: list[tuple[float, int]] = []
    valley_limit = max(1.0, typical * 0.42)
    for local_y in range(lo, hi + 1):
        density = float(smooth[local_y])
        if density > valley_limit:
            continue
        balance = abs(float(local_y) - center) / max(1.0, float(height))
        # Density dominates; balance only chooses among similarly clean valleys.
        score = density / max(1.0, typical) + 0.55 * balance
        candidates.append((score, local_y))
    if not candidates:
        return None

    for _score, local_y in sorted(candidates, key=lambda item: item[0]):
        upper = _trim_box_to_ink(ink, (x0, y0, x1, y0 + local_y))
        lower = _trim_box_to_ink(ink, (x0, y0 + local_y, x1, y1))
        if upper is None or lower is None:
            continue
        if not _valid_single_head_box(ink, upper, line_height, relaxed_height=True):
            continue
        if not _valid_single_head_box(ink, lower, line_height, relaxed_height=True):
            continue

        upper_h = upper[3] - upper[1]
        lower_h = lower[3] - lower[1]
        ratio = max(upper_h, lower_h) / float(max(1, min(upper_h, lower_h)))
        if ratio > 1.85:
            continue
        return upper, lower
    return None


def _split_stacked_heads(
    ink: np.ndarray,
    box: tuple[int, int, int, int],
    line_height: float,
) -> list[tuple[int, int, int, int]]:
    """Return one or more physical head boxes from a grouped vertical region."""
    pending = [box]
    output: list[tuple[int, int, int, int]] = []
    # At most four physical heads may originate from one accidental group. The
    # guard prevents pathological noise chains from recursively fragmenting.
    while pending and len(output) + len(pending) <= 4:
        current = pending.pop(0)
        split = _split_candidate_once(ink, current, line_height)
        if split is None:
            output.append(current)
        else:
            pending = [split[0], split[1], *pending]
    output.extend(pending)
    return output


def _candidate_boxes(
    ink: np.ndarray,
    line_height: float,
) -> list[tuple[int, int, int, int]]:
    result: list[tuple[int, int, int, int]] = []
    for grouped in _group_fragments(_large_fragments(ink, line_height), line_height):
        # A grouped region may contain two consecutive oversized heads. Permit a
        # taller pre-split envelope, but only emit pieces that independently pass
        # the original single-head geometry/density checks.
        group_height = grouped[3] - grouped[1]
        if group_height > line_height * 7.20:
            continue
        pieces = _split_stacked_heads(ink, grouped, line_height)
        for box in pieces:
            trimmed = _trim_box_to_ink(ink, box)
            if trimmed is None:
                continue
            if not _valid_single_head_box(ink, trimmed, line_height):
                continue
            result.append(trimmed)
    return result


def detect_ordinary_large_head_entries(
    image: Image.Image,
    understanding: Any,
    settings: AppSettings,
) -> list[Entry]:
    """Detect oversized CJK display heads without using indent polarity."""
    if not _uses_cjk_large_heads(settings):
        return []

    layout = understanding.layout
    canonical = layout.transform.canonical_image_for_analysis(image.convert("RGB"))
    gray_page = np.asarray(canonical.convert("L"), dtype=np.uint8)
    line_height = max(8.0, float(getattr(layout, "ordinary_line_height", 1.0) or 1.0))
    found: list[Entry] = []

    for column in list(getattr(layout, "columns", []) or []):
        left = max(0, int(column.left))
        right = min(gray_page.shape[1], int(column.right))
        top = max(0, int(layout.body_top))
        bottom = min(gray_page.shape[0], int(layout.body_bottom))
        if right <= left or bottom <= top:
            continue

        gray = gray_page[top:bottom, left:right]
        if gray.size == 0:
            continue
        ink = gray <= _otsu(gray)
        for x0, y0, x1, y1 in _candidate_boxes(ink, line_height):
            height = float(y1 - y0)
            canonical_y = top + int(y0)
            source_x, source_y = layout.transform.canonical_to_source_point(
                int(column.left),
                canonical_y,
                layout.source_size,
            )
            found.append(Entry(
                word="",
                x=int(source_x),
                y=int(source_y),
                confidence=min(0.995, max(0.90, height / max(1.0, line_height * 2.5))),
                ocr_source="ordinary_large_head_evidence",
                issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
                ocr_visual_run_height=height,
                ocr_line_height_reference=line_height,
                ocr_leading_height_ratio=height / max(1.0, line_height),
                ocr_single_cjk=True,
                ocr_oversized_cjk=True,
            ))

    # One oversized object may overlap several recovered logical rows. Keep a
    # single evidence event per physical display head. Consecutive physical heads
    # survive because their top coordinates are separated by more than this
    # within-head tolerance after stacked-region splitting.
    found.sort(key=lambda item: (item.x, item.y))
    deduped: list[Entry] = []
    tolerance = max(4, round(line_height * 0.80))
    for entry in found:
        if any(
            abs(entry.x - prior.x) <= tolerance
            and abs(entry.y - prior.y) <= tolerance
            for prior in deduped
        ):
            continue
        deduped.append(entry)
    return deduped
