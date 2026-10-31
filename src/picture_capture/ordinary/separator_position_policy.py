from __future__ import annotations

"""Ordinary/OCR marker position choice; no persistent state or output mutation.

processing_core retains historical private entrypoints and snapshots current
facade-patchable OCR-score, layout and numeric helpers at each call.
"""

from collections.abc import Callable
from typing import Any
import numpy as np
from PIL import Image, ImageOps
from ..models import Entry, AppSettings


def is_single_cjk_headword(word: str) -> bool:
    """Return True only for one normalized Han ideograph."""
    text = str(word or "").strip()
    if len(text) != 1:
        return False
    code = ord(text)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x323AF
    )


def separator_whitespace_score(
    image: Image.Image,
    entry: Entry,
    geometry: Any,
    settings: AppSettings,
    gray: np.ndarray | None = None,
    *,
    np_module: Any = np,
    image_ops: Any = ImageOps,
    normalize_rgb_fn: Callable[[Image.Image], Image.Image],
    column_fn: Callable[[int, Any, int], int],
    source_edge_fn: Callable[[Any, int, int], tuple[int, int]],
    otsu_fn: Callable[[np.ndarray], int],
) -> float | None:
    """Return 0..1 local blank-boundary evidence at one marker Y."""
    if geometry.transform.kind not in {"identity", "mirror_x"}:
        return None
    if gray is None:
        gray = np_module.asarray(image_ops.grayscale(normalize_rgb_fn(image)), dtype=np_module.uint8)
    if gray.size == 0:
        return None
    y = max(0, min(gray.shape[0] - 1, int(entry.y)))
    try:
        col = column_fn(int(entry.x), geometry, y)
        edge_x, direction = source_edge_fn(geometry, col, y)
    except (IndexError, ValueError, RuntimeError):
        return None
    column_width = max(
        20,
        int(geometry.column_widths[col])
        if col < len(geometry.column_widths) else int(getattr(settings, "column_width", 200) or 200),
    )
    character_height = max(
        4, int(round(float(getattr(settings, "character_height", 26) or 26)))
    )
    roi_width = max(
        24,
        min(round(column_width * 0.38), round(character_height * 9.0)),
    )
    other_x = int(edge_x) + int(direction) * int(roi_width)
    x0 = max(0, min(int(edge_x), int(other_x)))
    x1 = min(gray.shape[1], max(int(edge_x), int(other_x)) + 1)
    if x1 - x0 < 12:
        return None

    vertical_radius = max(4, round(character_height * 0.65))
    n0 = max(0, y - vertical_radius)
    n1 = min(gray.shape[0], y + vertical_radius + 1)
    neighborhood = gray[n0:n1, x0:x1]
    if neighborhood.size == 0:
        return None
    threshold = otsu_fn(neighborhood)

    row_scores: list[float] = []
    for yy in range(max(0, y - 1), min(gray.shape[0], y + 2)):
        row = gray[yy, x0:x1]
        if row.size:
            ink_ratio = float(np_module.mean(row <= threshold))
            row_scores.append(1.0 - ink_ratio)
    if not row_scores:
        return None
    return float(np_module.median(np_module.asarray(row_scores, dtype=float)))


def prefer_ocr_separator_position(
    image: Image.Image | None,
    ordinary: Entry,
    ocr: Entry,
    geometry: Any,
    settings: AppSettings,
    gray: np.ndarray | None = None,
    *,
    score_fn: Callable[..., float | None],
    single_cjk_fn: Callable[[str], bool],
) -> tuple[bool, float | None, float | None]:
    """Choose OCR Y only when its local blank boundary is materially stronger."""
    if image is None:
        return single_cjk_fn(ocr.word), None, None
    ordinary_score = score_fn(
        image, ordinary, geometry, settings, gray,
    )
    ocr_score = score_fn(
        image, ocr, geometry, settings, gray,
    )
    if ordinary_score is None or ocr_score is None:
        return single_cjk_fn(ocr.word), ordinary_score, ocr_score

    single_cjk = single_cjk_fn(ocr.word)
    # Keep the historical preferred source when both markers already sit in
    # equally clean whitespace. Switch only for a clear image-derived gain.
    margin = 0.035 if single_cjk else 0.055
    minimum_good = 0.94
    if ocr_score >= minimum_good and ocr_score >= ordinary_score + margin:
        return True, ordinary_score, ocr_score
    if ordinary_score >= minimum_good and ordinary_score >= ocr_score + margin:
        return False, ordinary_score, ocr_score
    return single_cjk, ordinary_score, ocr_score
