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

The final detector also owns the former runtime hardening statically: page-
observed ordinary-row scale, the shared column-drift left analysis band, and
strict row-front authorization. Bootstrap/import order therefore cannot select
a weaker large-head detector.
"""

from typing import Any

import numpy as np
from PIL import Image

from .models import AppSettings, Entry
from .ordinary_large_head_role_guard import (
    _nearest_row,
    strict_candidate_starts_at_row_front,
)
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


def _recover_oversized_front_lane(
    ink: np.ndarray,
    grouped: tuple[int, int, int, int],
    line_height: float,
) -> list[tuple[int, int, int, int]]:
    """Rescue separate tall glyphs from an anomalously long/wide group.

    Transitive fragment-neighbor grouping can link successive display heads
    through adjacent brackets, phonetics and definition strokes. Split only
    such rejected groups, using real blank horizontal bands inside a narrow
    *leading single-glyph corridor*. Ordinary body glyphs do not pass the
    unchanged single-head size filter, and the caller still applies the
    original strict physical row-front authorization.
    """
    x0, y0, x1, y1 = grouped
    reference = max(8.0, float(line_height))
    # The first glyph has a finite width; do not let the bracket word or
    # phonetic annotation hundreds of pixels farther right join its envelope.
    strip_right = min(int(x1), int(x0) + max(16, round(reference * 3.40)))
    if strip_right <= x0 or y1 <= y0:
        return []
    band = np.asarray(ink[y0:y1, x0:strip_right], dtype=bool)
    if not band.size:
        return []
    active = np.flatnonzero(np.count_nonzero(band, axis=1) >= 2)
    if active.size == 0:
        return []

    # Tiny blank gaps within a Han character must not split a radical into
    # separate candidates. Printed spaces between consecutive headwords are
    # much larger (~0.4 reference on the problematic dictionary page).
    max_internal_gap = max(2, round(reference * 0.14))
    ranges: list[tuple[int, int]] = []
    start = last = int(active[0])
    for at in active[1:]:
        at = int(at)
        if at - last > max_internal_gap + 1:
            ranges.append((start, last + 1))
            start = at
        last = at
    ranges.append((start, last + 1))

    recovered: list[tuple[int, int, int, int]] = []
    for start, end in ranges:
        candidate = _trim_box_to_ink(
            ink, (x0, y0 + start, strip_right, y0 + end),
        )
        if candidate is None:
            continue
        if _valid_single_head_box(ink, candidate, reference):
            recovered.append(candidate)
    return recovered


def _candidate_boxes(
    ink: np.ndarray,
    line_height: float,
    diagnostic_boxes: list[dict[str, Any]] | None = None,
) -> list[tuple[int, int, int, int]]:
    result: list[tuple[int, int, int, int]] = []
    for grouped in _group_fragments(_large_fragments(ink, line_height), line_height):
        # A grouped region may contain successive oversized heads connected
        # through their nearby text. Recover individual printed front glyphs
        # *before* discarding the oversized envelope.
        group_width = grouped[2] - grouped[0]
        group_height = grouped[3] - grouped[1]
        too_tall = group_height > line_height * 7.20
        pieces = (
            [] if too_tall else _split_stacked_heads(ink, grouped, line_height)
        )
        normal_valid = bool(
            pieces and all(
                _valid_single_head_box(ink, piece, line_height)
                for piece in pieces
            )
        )
        needs_recovery = too_tall or (
            not normal_valid
            and group_height >= line_height * 1.65
            and group_width > line_height * 3.80
        )
        if needs_recovery:
            recovered = _recover_oversized_front_lane(
                ink, grouped, line_height,
            )
            if recovered:
                if diagnostic_boxes is not None:
                    diagnostic_boxes.append({
                        "box": grouped, "reason": "split_parent",
                        "recovered_count": len(recovered),
                    })
                    diagnostic_boxes.extend({
                        "box": box, "reason": "geometry_pass",
                        "parent": grouped,
                    } for box in recovered)
                result.extend(recovered)
                continue
        if too_tall:
            if diagnostic_boxes is not None:
                diagnostic_boxes.append({"box": grouped, "reason": "group_too_tall"})
            continue
        for box in pieces:
            trimmed = _trim_box_to_ink(ink, box)
            if trimmed is None:
                continue
            valid = _valid_single_head_box(ink, trimmed, line_height)
            if diagnostic_boxes is not None:
                diagnostic_boxes.append({
                    "box": trimmed,
                    "reason": "geometry_pass" if valid else "size_or_density",
                })
            if not valid:
                continue
            result.append(trimmed)
    return result


def observed_body_line_reference(layout: Any) -> float:
    """Return a conservative ordinary-row height for large-head comparison."""
    baseline = max(
        8.0,
        float(getattr(layout, "ordinary_line_height", 1.0) or 1.0),
    )
    body_heights: list[float] = []
    all_heights: list[float] = []
    for column in list(getattr(layout, "columns", []) or []):
        for line in list(getattr(column, "lines", []) or []):
            try:
                height = float(getattr(line, "y1")) - float(getattr(line, "y0"))
            except (AttributeError, TypeError, ValueError):
                continue
            if height <= 0:
                continue
            if baseline * 0.42 <= height <= baseline * 2.20:
                all_heights.append(height)
                if str(getattr(line, "role", "body") or "body") == "body":
                    body_heights.append(height)

    samples = body_heights if len(body_heights) >= 8 else all_heights
    if len(samples) < 8:
        return baseline

    values = np.asarray(samples, dtype=float)
    center = float(np.median(values))
    deviation = np.abs(values - center)
    mad = float(np.median(deviation)) if deviation.size else 0.0
    if mad > 0:
        kept = values[deviation <= max(2.0, 3.5 * mad)]
        if kept.size >= 6:
            center = float(np.median(kept))

    return float(max(baseline, min(center, baseline * 1.80)))


def detect_ordinary_large_head_entries(
    image: Image.Image,
    understanding: Any,
    settings: AppSettings,
    *,
    diagnostics: list[dict[str, Any]] | None = None,
) -> list[Entry]:
    """Detect row-leading oversized CJK heads; optional read-only candidate trace.

    The default call path and emitted Entry list are unchanged. Diagnostics
    records geometry/row-front/strong-evidence decisions before any Layout
    role mutation; it is only populated when explicitly requested by the UI.
    """
    from .layout_column_drift import _analysis_left_for_column

    if not _uses_cjk_large_heads(settings):
        return []

    layout = understanding.layout
    canonical = layout.transform.canonical_image_for_analysis(image.convert("RGB"))
    try:
        gray_page = np.asarray(canonical.convert("L"), dtype=np.uint8)
        line_height = observed_body_line_reference(layout)
        found: list[Entry] = []
        columns = list(getattr(layout, "columns", []) or [])
        top = max(0, int(getattr(layout, "body_top", 0) or 0))
        bottom = min(
            gray_page.shape[0],
            int(getattr(layout, "body_bottom", gray_page.shape[0]) or gray_page.shape[0]),
        )

        for position, column in enumerate(columns):
            semantic_left = max(0, int(getattr(column, "left", 0) or 0))
            semantic_right = min(
                gray_page.shape[1],
                int(getattr(column, "right", semantic_left + 1) or semantic_left + 1),
            )
            analysis_left = _analysis_left_for_column(columns, position, line_height)
            if semantic_right <= analysis_left or bottom <= top:
                continue

            gray = gray_page[top:bottom, analysis_left:semantic_right]
            if gray.size == 0:
                continue
            ink = gray <= _otsu(gray)
            local_shift = int(analysis_left - semantic_left)

            observed_boxes: list[dict[str, Any]] | None = (
                [] if diagnostics is not None else None
            )
            candidates = _candidate_boxes(ink, line_height, observed_boxes)
            if diagnostics is not None and observed_boxes is not None:
                for observed in observed_boxes:
                    x0, y0, x1, y1 = observed["box"]
                    canonical_box = (
                        analysis_left + int(x0), top + int(y0),
                        analysis_left + int(x1), top + int(y1),
                    )
                    status = str(observed["reason"])
                    if status == "geometry_pass":
                        semantic_box = (
                            int(x0 + local_shift), int(y0),
                            int(x1 + local_shift), int(y1),
                        )
                        if not strict_candidate_starts_at_row_front(
                            column, semantic_box, line_height,
                        ):
                            status = "rejected_row_front"
                        elif float(y1-y0) / max(1.0, line_height) < 1.65:
                            status = "rejected_weak"
                        else:
                            status = "accepted"
                    record: dict[str, Any] = {
                        "column": int(position),
                        "canonical_box": canonical_box,
                        "source_box": tuple(map(int,
                            layout.transform.canonical_box_to_source(
                                canonical_box, layout.source_size,
                            ),
                        )),
                        "reference_height": round(float(line_height), 2),
                        "height_ratio": round((y1-y0) / max(1.0, line_height), 3),
                        "status": status,
                        "detector_output": False,
                    }
                    if "recovered_count" in observed:
                        record["recovered_count"] = int(observed["recovered_count"])
                    if "parent" in observed:
                        px0, py0, px1, py1 = observed["parent"]
                        parent_canonical = (
                            analysis_left + int(px0), top + int(py0),
                            analysis_left + int(px1), top + int(py1),
                        )
                        record["parent_source_box"] = tuple(map(int,
                            layout.transform.canonical_box_to_source(
                                parent_canonical, layout.source_size,
                            ),
                        ))
                    diagnostics.append(record)

            for raw_box in candidates:
                x0, y0, x1, y1 = raw_box
                # Candidate X is local to the widened analysis band. Convert it
                # back to semantic-column-local coordinates before comparing it
                # with LayoutLine.first_x / anchor_x.
                semantic_box = (
                    int(x0 + local_shift),
                    int(y0),
                    int(x1 + local_shift),
                    int(y1),
                )
                if not strict_candidate_starts_at_row_front(
                    column,
                    semantic_box,
                    line_height,
                ):
                    continue

                # A large glyph may begin below the actual printed row
                # because a small superscript/number precedes it. Once the
                # physical row-front guard has authorized the glyph, the
                # separator belongs to the ROW, not the top of its ink box.
                # This also prevents role fusion from promoting a second-row
                # fragment when a tall glyph starts >0.15 row below row top.
                start_row = _nearest_row(column, semantic_box, line_height)
                if start_row is None:
                    continue
                height = float(y1 - y0)
                canonical_y = top + int(getattr(start_row, "y0"))
                source_x, source_y = layout.transform.canonical_to_source_point(
                    semantic_left,
                    canonical_y,
                    layout.source_size,
                )
                found.append(Entry(
                    word="",
                    x=int(source_x),
                    y=int(source_y),
                    confidence=min(
                        0.995,
                        max(0.90, height / max(1.0, line_height * 2.5)),
                    ),
                    ocr_source="ordinary_large_head_evidence",
                    issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
                    ocr_visual_run_height=height,
                    ocr_line_height_reference=line_height,
                    ocr_leading_height_ratio=height / max(1.0, line_height),
                    ocr_single_cjk=True,
                    ocr_oversized_cjk=True,
                ))
    finally:
        try:
            canonical.close()
        except Exception:
            pass

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
    if diagnostics is not None:
        # Provenance of what the detector actually returned after its own
        # de-duplication. A weak size observation can be returned here yet
        # subsequently rejected by strong_ordinary_large_head in role fusion.
        for row in diagnostics:
            if row["status"] not in {"accepted", "rejected_weak"}:
                continue
            box = row["source_box"]
            for entry in deduped:
                if (
                    abs(int(entry.x) - int(layout.transform.canonical_to_source_point(
                        layout.columns[int(row["column"])].left,
                        row["canonical_box"][1], layout.source_size,
                    )[0])) <= tolerance
                    and abs(int(entry.y) - int(layout.transform.canonical_to_source_point(
                        layout.columns[int(row["column"])].left,
                        row["canonical_box"][1], layout.source_size,
                    )[1])) <= tolerance
                ):
                    row["detector_output"] = True
                    break
    return deduped


__all__ = [
    "detect_ordinary_large_head_entries",
    "observed_body_line_reference",
]
