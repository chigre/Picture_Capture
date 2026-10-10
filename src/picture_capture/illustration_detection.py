"""Core connected-component illustration detection, without processing-core imports."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from .models import AppSettings, PolygonRegion
from .illustration_candidate_size import illustration_candidate_min_dimensions


AUTO_ILLUSTRATION_LABEL_TOKEN = "|AUTO_"


def _rle_components(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """Connected components for a small binary mask using row runs.

    This avoids an OpenCV/SciPy dependency.  The detector works on a reduced
    analysis image, so run-length union/find is both fast and memory-light.
    Returned boxes are ``(x0, y0, x1, y1, area)`` with x1/y1 exclusive.
    """
    mask = np.asarray(mask, dtype=bool)
    h, w = mask.shape
    parent: list[int] = []
    rank: list[int] = []
    boxes: list[list[int]] = []

    def make(x0: int, x1: int, y: int) -> int:
        i = len(parent)
        parent.append(i); rank.append(0)
        boxes.append([x0, y, x1, y + 1, x1 - x0])
        return i

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> int:
        ra, rb = find(a), find(b)
        if ra == rb:
            return ra
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1
        return ra

    prev: list[tuple[int, int, int]] = []
    for y in range(h):
        row = mask[y]
        padded = np.r_[False, row, False].astype(np.int8)
        changes = np.diff(padded)
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1)
        current: list[tuple[int, int, int]] = []
        j = 0
        for x0, x1 in zip(starts.tolist(), ends.tolist()):
            cid = make(x0, x1, y)
            while j < len(prev) and prev[j][1] < x0 - 1:
                j += 1
            k = j
            while k < len(prev) and prev[k][0] <= x1 + 1:
                px0, px1, pid = prev[k]
                if px1 >= x0 - 1:
                    union(cid, pid)
                k += 1
            current.append((x0, x1, cid))
        prev = current

    merged: dict[int, list[int]] = {}
    for i, box in enumerate(boxes):
        r = find(i)
        target = merged.setdefault(r, [box[0], box[1], box[2], box[3], 0])
        target[0] = min(target[0], box[0]); target[1] = min(target[1], box[1])
        target[2] = max(target[2], box[2]); target[3] = max(target[3], box[3])
        target[4] += box[4]
    return [tuple(v) for v in merged.values()]


def _box_gap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int]:
    ax0, ay0, ax1, ay1 = a; bx0, by0, bx1, by1 = b
    gx = max(0, max(ax0, bx0) - min(ax1, bx1))
    gy = max(0, max(ay0, by0) - min(ay1, by1))
    return gx, gy


def _merge_nearby_boxes(boxes: list[tuple[int, int, int, int]], gap: int) -> list[tuple[int, int, int, int]]:
    boxes = [tuple(map(int, b)) for b in boxes]
    changed = True
    while changed and len(boxes) > 1:
        changed = False
        out: list[tuple[int, int, int, int]] = []
        used = [False] * len(boxes)
        for i, box in enumerate(boxes):
            if used[i]:
                continue
            x0, y0, x1, y1 = box
            used[i] = True
            for j in range(i + 1, len(boxes)):
                if used[j]:
                    continue
                other = boxes[j]
                gx, gy = _box_gap((x0, y0, x1, y1), other)
                # Merge close fragments of one drawing, but do not bridge two
                # separate text columns or distant illustrations.
                vertical_overlap = min(y1, other[3]) - max(y0, other[1])
                horizontal_overlap = min(x1, other[2]) - max(x0, other[0])
                if (gx <= gap and gy <= gap and (vertical_overlap > 0 or horizontal_overlap > 0)):
                    x0 = min(x0, other[0]); y0 = min(y0, other[1])
                    x1 = max(x1, other[2]); y1 = max(y1, other[3])
                    used[j] = True; changed = True
            out.append((x0, y0, x1, y1))
        boxes = out
    return boxes


def _polygon_bbox(region: PolygonRegion) -> tuple[int, int, int, int] | None:
    if len(region.points) < 3:
        return None
    xs = [p[0] for p in region.points]; ys = [p[1] for p in region.points]
    return min(xs), min(ys), max(xs), max(ys)


def _overlap_fraction(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    return inter / area


def is_auto_illustration_region(region: PolygonRegion) -> bool:
    return AUTO_ILLUSTRATION_LABEL_TOKEN in str(region.label or "").upper()



def detect_illustration_regions_from_image(
    image: Image.Image,
    settings: AppSettings,
    *,
    analysis_column_width: int = 520,
    profile_page_index: int = 0,
    page_geometry_context,
    source_px,
    adaptive_dark_mask,
) -> list[PolygonRegion]:
    """Detect automatic PPP illustration candidates from an in-memory page.

    This is the single component detector shared by historical path-based
    PPP auto-detection and optional Layout illustration masking.
    """
    source, effective, analysis_source, geometry = page_geometry_context(
        image,
        settings,
        int(profile_page_index),
    )
    work_image: Image.Image | None = None
    try:
        work_image = geometry.transform.canonical_image_for_analysis(analysis_source)
        source_margin = max(
            2,
            source_px(
                max(0, int(getattr(effective, "illustration_detect_padding", 8)))
            ),
        )
        source_margin_right = max(
            source_margin,
            source_px(
                max(
                    0,
                    int(getattr(effective, "illustration_detect_right_padding", 16)),
                )
            ),
        )
        results: list[PolygonRegion] = []
        for column, start in enumerate(geometry.column_starts):
            width = geometry.column_widths[column]
            base_x0 = max(0, int(start))
            base_x1 = min(work_image.width, int(start + width))
            if column + 1 < len(geometry.column_starts):
                next_start = int(geometry.column_starts[column + 1])
                free_right = max(0, next_start - base_x1)
                right_room = min(
                    max(source_margin_right, free_right // 2),
                    max(source_margin_right, round(width * 0.10)),
                )
            else:
                free_right = max(0, work_image.width - base_x1)
                right_room = min(
                    free_right,
                    max(source_margin_right, round(width * 0.08)),
                )
            x0 = base_x0
            x1 = min(work_image.width, base_x1 + max(0, right_room))
            y0 = max(0, int(geometry.top))
            y1 = min(work_image.height, int(geometry.bottom))
            if x1 - x0 < 40 or y1 - y0 < 80:
                continue

            crop = work_image.crop((x0, y0, x1, y1)).convert("L")
            try:
                a_scale = min(1.0, analysis_column_width / max(1, crop.width))
                aw = max(1, round(crop.width * a_scale))
                ah = max(1, round(crop.height * a_scale))
                small = (
                    crop
                    if a_scale == 1.0
                    else crop.resize((aw, ah), Image.Resampling.BILINEAR)
                )
                try:
                    adaptive = adaptive_dark_mask(small, 19, 16)
                    arr = np.asarray(small, dtype=np.uint8)
                    dark = np.logical_or(adaptive, arr < int(effective.illustration_detect_gray_threshold))
                    mask_img = Image.fromarray(
                        dark.astype(np.uint8) * 255,
                        mode="L",
                    )
                    try:
                        joined = (
                            np.asarray(
                                mask_img.filter(ImageFilter.MaxFilter(3)),
                                dtype=np.uint8,
                            )
                            > 0
                        )
                    finally:
                        mask_img.close()

                    comps = _rle_components(joined)
                    min_w, min_h = illustration_candidate_min_dimensions(effective, aw, ah)
                    candidates: list[tuple[int, int, int, int]] = []
                    for cx0, cy0, cx1, cy1, area in comps:
                        bw = cx1 - cx0
                        bh = cy1 - cy0
                        bbox_area = bw * bh
                        if bw < min_w or bh < min_h:
                            continue
                        occupancy = area / max(1, bbox_area)
                        if occupancy < effective.illustration_detect_min_occupancy_percent / 100.0:
                            continue
                        if bw / max(1, bh) > 7.0 and bh < 0.08 * ah:
                            continue
                        candidates.append((cx0, cy0, cx1, cy1))

                    gap = max(5, round(0.018 * aw))
                    candidates = _merge_nearby_boxes(candidates, gap)
                    for cx0, cy0, cx1, cy1 in candidates:
                        bw = cx1 - cx0
                        bh = cy1 - cy0
                        if bh < min_h or bw < min_w:
                            continue
                        sx0 = x0 + round(cx0 / a_scale) - source_margin
                        sy0 = y0 + round(cy0 / a_scale) - source_margin
                        sx1 = x0 + round(cx1 / a_scale) + source_margin_right
                        sy1 = y0 + round(cy1 / a_scale) + source_margin
                        sx0 = max(x0, sx0)
                        sy0 = max(y0, sy0)
                        sx1 = min(x1, sx1)
                        sy1 = min(y1, sy1)
                        if sx1 - sx0 < 8 or sy1 - sy0 < 8:
                            continue
                        results.append(
                            PolygonRegion(
                                "",
                                [
                                    (sx0, sy0),
                                    (sx1, sy0),
                                    (sx1, sy1),
                                    (sx0, sy1),
                                ],
                            )
                        )
                finally:
                    if small is not crop:
                        small.close()
            finally:
                crop.close()

        if geometry.transform.kind == "identity":
            return results
        return [
            PolygonRegion(
                region.label,
                [geometry.canonical_to_source(x, y) for x, y in region.points],
            )
            for region in results
        ]
    finally:
        if work_image is not None:
            try:
                work_image.close()
            except Exception:
                pass
        try:
            if analysis_source is not source:
                analysis_source.close()
        except Exception:
            pass
        try:
            if source is not image:
                source.close()
        except Exception:
            pass


