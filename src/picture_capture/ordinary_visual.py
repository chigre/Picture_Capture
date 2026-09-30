from __future__ import annotations

"""OCR-independent visual recovery for ordinary dictionary drawing.

The legacy VB detector is deliberately retained as the primary ordinary path.
This module only recovers entry starts that a single left-edge lane cannot see:
repeated indented marker lanes (notably CJK ``【...】`` subentries) and oversized
display headwords.  It never recognizes text.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .image_utils import normalize_page_rgb
from .models import AppSettings, Entry


@dataclass(slots=True)
class _VisualLine:
    y0: int
    y1: int
    start: int
    patch: np.ndarray
    max_similarity: float = 0.0


@dataclass(slots=True)
class _IndentedLaneEvidence:
    column: int
    top: int
    ink: np.ndarray
    lines: list[_VisualLine]
    baseline: float
    lane_center: float
    marker_rows: list[_VisualLine]
    cluster: list[_VisualLine]


def _otsu(gray: np.ndarray) -> int:
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = float(hist.sum())
    if total <= 0:
        return 127
    probability = hist / total
    omega = np.cumsum(probability)
    means = np.cumsum(probability * np.arange(256, dtype=np.float64))
    global_mean = means[-1]
    denominator = omega * (1.0 - omega)
    score = np.zeros(256, dtype=np.float64)
    valid = denominator > 1e-12
    score[valid] = ((global_mean * omega[valid] - means[valid]) ** 2) / denominator[valid]
    return int(min(235, max(40, int(np.argmax(score)))))


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    values = np.asarray(mask, dtype=bool).tolist()
    result: list[tuple[int, int]] = []
    i = 0
    while i < len(values):
        if not values[i]:
            i += 1
            continue
        end = i + 1
        while end < len(values) and values[end]:
            end += 1
        result.append((i, end))
        i = end
    return result


def _fill_short_gaps(mask: np.ndarray, maximum: int) -> np.ndarray:
    result = np.asarray(mask, dtype=bool).copy()
    maximum = max(0, int(maximum))
    if maximum <= 0:
        return result
    i = 0
    while i < len(result):
        if result[i]:
            i += 1
            continue
        end = i + 1
        while end < len(result) and not result[end]:
            end += 1
        if i > 0 and end < len(result) and end - i <= maximum:
            result[i:end] = True
        i = end
    return result


def _cjk_visual_mode(settings: AppSettings) -> bool:
    profile_id = str(getattr(settings, "dictionary_profile_id", "") or "").lower()
    ocr_language = str(getattr(settings, "ocr_language", "") or "").lower()
    paddle_language = str(getattr(settings, "paddle_language", "") or "").lower()
    return bool(
        "cjk" in profile_id
        or any(token in ocr_language for token in ("chi_sim", "chi_tra", "chinese", "han"))
        or paddle_language in {"ch", "chi_sim", "chi_tra", "chinese_cht"}
    )


def _source_edge(geometry: Any, column: int, y: int) -> tuple[int, int]:
    transform = getattr(geometry, "transform", None)
    kind = str(getattr(transform, "kind", "identity") or "identity")
    if kind not in {"identity", "mirror_x"}:
        raise RuntimeError("ordinary visual lanes support horizontal source-Y layouts only")
    canonical_x = int(round(geometry.x_at(column, int(y))))
    source_x, source_y = geometry.canonical_to_source(canonical_x, int(y))
    next_x, next_y = geometry.canonical_to_source(canonical_x + 1, int(y))
    if int(source_y) != int(y) or int(next_y) != int(y):
        raise RuntimeError("ordinary visual lane transform is not horizontal")
    return int(source_x), 1 if int(next_x) >= int(source_x) else -1


def _column_band_gray(
    source: Image.Image,
    geometry: Any,
    column: int,
    top: int,
    bottom: int,
) -> np.ndarray:
    gray = np.asarray(ImageOps.grayscale(source), dtype=np.uint8)
    height, source_width = gray.shape
    top = max(0, min(height - 1, int(top)))
    bottom = max(top + 1, min(height, int(bottom)))
    column_width = max(16, int(geometry.column_widths[column]))
    output = np.full((bottom - top, column_width), 255, dtype=np.uint8)
    offsets = np.arange(column_width, dtype=np.int64)
    for local_y, source_y in enumerate(range(top, bottom)):
        edge, direction = _source_edge(geometry, column, source_y)
        xs = edge + direction * offsets
        valid = (xs >= 0) & (xs < source_width)
        if bool(valid.any()):
            output[local_y, valid] = gray[source_y, xs[valid]]
    return output


def _first_ink_lines(
    ink: np.ndarray,
    character_height: int,
) -> list[_VisualLine]:
    width = ink.shape[1]
    active = ink.sum(axis=1) >= max(2, round(width * 0.003))
    active = _fill_short_gaps(active, max(1, round(character_height * 0.12)))
    output: list[_VisualLine] = []
    for y0, y1 in _runs(active):
        line_height = y1 - y0
        if not (character_height * 0.30 <= line_height <= character_height * 1.90):
            continue
        line = ink[y0:y1]
        sturdy = line.sum(axis=0) >= max(1, round(line_height * 0.08))
        columns = np.flatnonzero(sturdy)
        if columns.size == 0:
            continue
        start = int(columns[0])
        patch_y0 = max(0, y0 - round(character_height * 0.12))
        patch_y1 = min(ink.shape[0], y1 + round(character_height * 0.12))
        patch_x0 = max(0, start - round(character_height * 0.08))
        patch_x1 = min(ink.shape[1], start + round(character_height * 1.00))
        output.append(_VisualLine(
            int(y0), int(y1), start,
            ink[patch_y0:patch_y1, patch_x0:patch_x1].copy(),
        ))
    return output


def _body_lane(lines: list[_VisualLine], column_width: int, character_height: int) -> float | None:
    maximum = min(column_width * 0.18, character_height * 4.0)
    starts = [line.start for line in lines if line.start <= maximum]
    if len(starts) < 4:
        return None
    bin_width = max(3, round(character_height * 0.25))
    counts: dict[int, int] = {}
    for start in starts:
        key = int(round(start / bin_width))
        counts[key] = counts.get(key, 0) + 1
    key = max(counts, key=lambda item: (counts[item], -item))
    selected = [start for start in starts if int(round(start / bin_width)) == key]
    return float(np.median(np.asarray(selected, dtype=float)))


def _patch_similarity(left: np.ndarray, right: np.ndarray) -> float:
    if left.size == 0 or right.size == 0:
        return 0.0
    left_image = Image.fromarray((left.astype(np.uint8) * 255), mode="L")
    right_image = Image.fromarray((right.astype(np.uint8) * 255), mode="L")
    try:
        left_values = np.asarray(
            left_image.resize((12, 24), Image.Resampling.NEAREST),
            dtype=np.float32,
        ).ravel()
        right_values = np.asarray(
            right_image.resize((12, 24), Image.Resampling.NEAREST),
            dtype=np.float32,
        ).ravel()
    finally:
        left_image.close()
        right_image.close()
    left_values -= float(left_values.mean())
    right_values -= float(right_values.mean())
    left_norm = float(np.linalg.norm(left_values))
    right_norm = float(np.linalg.norm(right_values))
    if left_norm <= 1e-6 or right_norm <= 1e-6:
        return 0.0
    return float(np.dot(left_values, right_values) / (left_norm * right_norm))


def _cluster_lines(lines: list[_VisualLine], tolerance: float) -> list[list[_VisualLine]]:
    clusters: list[list[_VisualLine]] = []
    for line in sorted(lines, key=lambda item: item.start):
        target: list[_VisualLine] | None = None
        for cluster in clusters:
            center = float(np.median([item.start for item in cluster]))
            if abs(float(line.start) - center) <= tolerance:
                target = cluster
                break
        if target is None:
            clusters.append([line])
        else:
            target.append(line)
    return clusters


def _separator_above(
    ink: np.ndarray,
    line_y: int,
    character_height: int,
) -> tuple[int | None, float]:
    search = max(5, round(character_height * 1.05))
    top = max(0, int(line_y) - search)
    bottom = max(top, int(line_y))
    if bottom <= top:
        return None, 1.0
    # A separator is a page-row property. Use nearly the entire column rather
    # than only the indented lane; this avoids choosing whitespace that exists
    # beside a wrapped definition line.
    span = max(16, min(ink.shape[1], round(ink.shape[1] * 0.97)))
    ratios = ink[top:bottom, :span].mean(axis=1)
    if ratios.size == 0:
        return None, 1.0
    minimum = float(ratios.min())
    if minimum > 0.025:
        return None, minimum

    clean = ratios <= max(0.0035, minimum + 0.0035)
    clean_runs = _runs(clean)
    if not clean_runs:
        index = int(np.argmin(ratios))
        return top + index, minimum

    # Prefer the clean run nearest the headword, but place the marker at the
    # start of that whitespace run so ascenders/diacritics from the new entry
    # cannot be cut away.
    run_start, _run_end = max(clean_runs, key=lambda pair: pair[1])
    return top + int(run_start), minimum


def _entry_column(entry: Entry, geometry: Any) -> int:
    u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
    return min(
        range(len(geometry.column_starts)),
        key=lambda column: abs(int(u) - int(geometry.x_at(column, int(v)))),
    )


def _duplicate(
    entries: list[Entry],
    geometry: Any,
    column: int,
    candidate_y: int,
    tolerance: int,
) -> bool:
    for entry in entries:
        if _entry_column(entry, geometry) != column:
            continue
        _u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        if abs(int(v) - int(candidate_y)) <= tolerance:
            return True
    return False


def _inside_sections(y: int, page_sections: list[Any] | None) -> bool:
    if not page_sections:
        return True
    return any(int(section.top_v) <= int(y) < int(section.bottom_v) for section in page_sections)


def _find_indented_lane_evidence(
    source: Image.Image,
    geometry: Any,
    settings: AppSettings,
) -> list[_IndentedLaneEvidence]:
    """Return strongly proven secondary entry lanes for the current page.

    A secondary lane is not inferred from indentation alone.  It must repeat,
    show a stable marker-like leading visual structure, and sit distinctly to
    the right of the dominant body-text lane.  The same evidence is reused for
    both recovery and polarity suppression so the two decisions cannot drift.
    """
    if not bool(getattr(settings, "profile_cjk_allow_bracketed_headword", True)):
        return []
    if not _cjk_visual_mode(settings):
        return []

    character_height = max(
        8, int(round(float(getattr(settings, "character_height", 26) or 26)))
    )
    evidence: list[_IndentedLaneEvidence] = []
    for column in range(len(geometry.column_starts)):
        top = max(0, int(geometry.top))
        bottom = min(source.height, int(geometry.bottom))
        band = _column_band_gray(source, geometry, column, top, bottom)
        threshold = _otsu(band)
        ink = band <= threshold
        lines = _first_ink_lines(ink, character_height)
        baseline = _body_lane(lines, ink.shape[1], character_height)
        if baseline is None:
            continue

        candidates = [
            line for line in lines
            if (
                baseline + character_height * 0.90
                <= line.start
                <= baseline + character_height * 3.70
            )
        ]
        clusters = _cluster_lines(candidates, character_height * 0.55)
        for cluster in clusters:
            if len(cluster) < 4:
                continue
            for line in cluster:
                similarities = [
                    _patch_similarity(line.patch, other.patch)
                    for other in cluster if other is not line
                ]
                line.max_similarity = max(similarities) if similarities else 0.0
            marker_rows = [line for line in cluster if line.max_similarity >= 0.50]
            if len(marker_rows) < 3 or len(marker_rows) / float(len(cluster)) < 0.45:
                continue
            lane_center = float(np.median([line.start for line in marker_rows]))
            # The secondary lane must be meaningfully distinct from body text.
            if lane_center - baseline < character_height * 0.85:
                continue
            evidence.append(_IndentedLaneEvidence(
                column=column,
                top=top,
                ink=ink,
                lines=lines,
                baseline=float(baseline),
                lane_center=lane_center,
                marker_rows=marker_rows,
                cluster=cluster,
            ))
    return evidence


def _line_after_separator(
    lines: list[_VisualLine],
    local_y: int,
    character_height: int,
) -> _VisualLine | None:
    """Return the text line that starts immediately after one separator marker."""
    lower = int(local_y) - max(2, round(character_height * 0.18))
    upper = int(local_y) + max(8, round(character_height * 1.35))
    candidates = [
        line for line in lines
        if lower <= int(line.y0) <= upper
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda line: abs(int(line.y0) - int(local_y)))


def _suppress_primary_body_lane_entries(
    source: Image.Image,
    entries: list[Entry],
    geometry: Any,
    settings: AppSettings,
    page_sections: list[Any] | None,
    evidence: list[_IndentedLaneEvidence],
) -> list[Entry]:
    """Remove legacy VB markers that belong to the proven body-text lane.

    In some CJK dictionaries the historical ordinary-mode prior is reversed:
    body/definition lines begin at the physical column edge, while true
    bracketed entries live on a repeated indented lane.  Once that secondary
    entry lane is proven from the page itself, keeping every legacy main-lane
    marker produces the exact inverted result reported by users.

    Suppression is deliberately conditional and conservative:
    * it runs only in columns with a strongly proven secondary lane;
    * it only removes automatic legacy ordinary markers;
    * the marker must resolve to a normal-height line on the dominant body lane;
    * oversized display heads are recovered afterwards by the independent
      connected-component detector.
    """
    if not evidence:
        return list(entries)

    character_height = max(
        8, int(round(float(getattr(settings, "character_height", 26) or 26)))
    )
    body_tolerance = max(5.0, character_height * 0.58)
    lane_by_column: dict[int, list[_IndentedLaneEvidence]] = {}
    for item in evidence:
        lane_by_column.setdefault(int(item.column), []).append(item)

    output: list[Entry] = []
    for entry in entries:
        source_name = str(getattr(entry, "ocr_source", "") or "")
        if source_name not in {"", "ordinary_vb"}:
            output.append(entry)
            continue

        column = _entry_column(entry, geometry)
        lane_evidence = lane_by_column.get(column, [])
        if not lane_evidence:
            output.append(entry)
            continue

        _u, canonical_v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        matched_body = False
        for item in lane_evidence:
            local_y = int(canonical_v) - int(item.top)
            line = _line_after_separator(
                item.lines, local_y, character_height,
            )
            if line is None:
                continue
            if abs(float(line.start) - float(item.baseline)) <= body_tolerance:
                matched_body = True
                break

        if matched_body:
            # Do not carry the legacy body-line false positive forward.  Any
            # true oversized main-lane head is independently re-added below.
            continue
        output.append(entry)
    return output


def _recover_indented_lanes(
    source: Image.Image,
    entries: list[Entry],
    geometry: Any,
    settings: AppSettings,
    page_sections: list[Any] | None,
    evidence: list[_IndentedLaneEvidence] | None = None,
) -> list[Entry]:
    if not bool(getattr(settings, "profile_cjk_allow_bracketed_headword", True)):
        return list(entries)
    if not _cjk_visual_mode(settings):
        return list(entries)

    character_height = max(
        8, int(round(float(getattr(settings, "character_height", 26) or 26)))
    )
    duplicate_tolerance = max(4, round(character_height * 0.50))
    recovered = list(entries)
    proven = (
        list(evidence)
        if evidence is not None
        else _find_indented_lane_evidence(source, geometry, settings)
    )

    for item in proven:
        column = int(item.column)
        for line in item.cluster:
            if abs(float(line.start) - item.lane_center) > character_height * 0.85:
                continue
            separator, blankness = _separator_above(
                item.ink, line.y0, character_height,
            )
            if separator is None:
                continue
            source_y = int(item.top) + int(separator)
            if not _inside_sections(source_y, page_sections):
                continue
            if _duplicate(
                recovered, geometry, column, source_y, duplicate_tolerance,
            ):
                continue
            marker_x, _direction = _source_edge(geometry, column, source_y)
            confidence = min(
                0.98,
                0.86
                + 0.08 * min(1.0, len(item.marker_rows) / 6.0)
                + 0.04 * max(0.0, min(1.0, line.max_similarity)),
            )
            recovered.append(Entry(
                word="",
                x=int(marker_x),
                y=int(source_y),
                confidence=float(round(confidence, 4)),
                ocr_source="ordinary_visual_lane",
                issue_type="ORDINARY_INDENTED_ENTRY_LANE",
            ))
    return recovered


def _components(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """Small run-length connected-component implementation."""
    mask = np.asarray(mask, dtype=bool)
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

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        if rank[left_root] < rank[right_root]:
            left_root, right_root = right_root, left_root
        parent[right_root] = left_root
        if rank[left_root] == rank[right_root]:
            rank[left_root] += 1

    previous: list[tuple[int, int, int]] = []
    for y, row in enumerate(mask):
        padded = np.r_[False, row, False].astype(np.int8)
        changes = np.diff(padded)
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1)
        current: list[tuple[int, int, int]] = []
        pointer = 0
        for x0, x1 in zip(starts.tolist(), ends.tolist()):
            component = make(x0, x1, y)
            while pointer < len(previous) and previous[pointer][1] < x0 - 1:
                pointer += 1
            other = pointer
            while other < len(previous) and previous[other][0] <= x1 + 1:
                px0, px1, previous_component = previous[other]
                if px1 >= x0 - 1:
                    union(component, previous_component)
                other += 1
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


def _recover_oversized_components(
    source: Image.Image,
    entries: list[Entry],
    geometry: Any,
    settings: AppSettings,
    page_sections: list[Any] | None,
) -> list[Entry]:
    if not bool(getattr(settings, "profile_cjk_allow_single_headword", True)):
        return list(entries)
    if not _cjk_visual_mode(settings):
        return list(entries)

    character_height = max(8, int(round(float(getattr(settings, "character_height", 26) or 26))))
    duplicate_tolerance = max(5, round(character_height * 0.65))
    recovered = list(entries)

    for column in range(len(geometry.column_starts)):
        top = max(0, int(geometry.top))
        bottom = min(source.height, int(geometry.bottom))
        analysis_width = min(
            max(80, round(character_height * 3.7)),
            max(80, int(geometry.column_widths[column])),
        )
        full_band = _column_band_gray(source, geometry, column, top, bottom)
        band = full_band[:, :analysis_width]
        threshold = _otsu(band)
        original_ink = band <= threshold
        ink_image = Image.fromarray((original_ink.astype(np.uint8) * 255), mode="L")
        try:
            joined = np.asarray(
                ink_image.filter(ImageFilter.MaxFilter(3)),
                dtype=np.uint8,
            ) > 0
        finally:
            ink_image.close()

        for x0, y0, x1, y1, _area in _components(joined):
            width = int(x1 - x0)
            height = int(y1 - y0)
            if height < round(character_height * 1.45):
                continue
            if height > round(character_height * 3.0):
                continue
            if width < round(character_height * 0.90):
                continue
            if x0 > round(character_height * 1.80):
                continue
            aspect = height / float(max(1, width))
            if not 0.55 <= aspect <= 2.40:
                continue
            roi = original_ink[max(0, y0):min(original_ink.shape[0], y1),
                               max(0, x0):min(original_ink.shape[1], x1)]
            if roi.size == 0 or float(roi.mean()) < 0.08:
                continue
            separator, blankness = _separator_above(
                full_band <= _otsu(full_band), y0, character_height,
            )
            if separator is None:
                continue
            source_y = top + int(separator)
            if not _inside_sections(source_y, page_sections):
                continue
            if _duplicate(
                recovered, geometry, column, source_y, duplicate_tolerance,
            ):
                continue
            marker_x, _direction = _source_edge(geometry, column, source_y)
            confidence = min(
                0.99,
                0.90 + 0.05 * min(1.0, height / float(character_height * 2.0))
                + 0.03 * max(0.0, 1.0 - blankness / 0.025),
            )
            recovered.append(Entry(
                word="",
                x=int(marker_x),
                y=int(source_y),
                confidence=float(round(confidence, 4)),
                ocr_source="ordinary_visual_head",
                issue_type="ORDINARY_OVERSIZED_HEAD_COMPONENT",
                ocr_visual_run_height=float(height),
                ocr_line_height_reference=float(character_height),
                ocr_single_cjk=True,
                ocr_oversized_cjk=True,
            ))
    return recovered


def recover_ordinary_visual_entries(
    image: Image.Image,
    entries: list[Entry],
    geometry: Any,
    settings: AppSettings,
    page_sections: list[Any] | None = None,
) -> list[Entry]:
    """Apply OCR-independent lane polarity, recovery and display-head detection."""
    source = normalize_page_rgb(image)
    kind = str(getattr(getattr(geometry, "transform", None), "kind", "identity") or "identity")
    if kind not in {"identity", "mirror_x"}:
        return list(entries)
    lane_evidence = _find_indented_lane_evidence(
        source, geometry, settings,
    )
    recovered = _suppress_primary_body_lane_entries(
        source,
        list(entries),
        geometry,
        settings,
        page_sections,
        lane_evidence,
    )
    recovered = _recover_indented_lanes(
        source,
        recovered,
        geometry,
        settings,
        page_sections,
        evidence=lane_evidence,
    )
    recovered = _recover_oversized_components(
        source, recovered, geometry, settings, page_sections,
    )
    return recovered
