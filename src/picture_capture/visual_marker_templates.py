from __future__ import annotations

"""Dictionary-specific visual marker templates.

The fixed-symbol parser deals with Unicode literals; this module complements it
with small project-level image templates captured from real scanned pages. The
stored representation is intentionally self-contained so a project remains
portable when the original source page path changes.
"""

from typing import Any, Iterable
import json
import math

import numpy as np
from PIL import Image


TEMPLATE_FORMAT_VERSION = 1
DEFAULT_TEMPLATE_SIZE = 32
VALID_TEMPLATE_ROLES = {"entry_marker", "bracket_open"}

# Symbols that may be entered without separators in Project Profile. Unknown
# multi-character tokens remain intact so custom markers are still possible.
KNOWN_SINGLE_MARKER_SYMBOLS = frozenset(
    "○◯◦●•◉◇◆□■△▽▷◁▲▼▶►◀【〔［[「『〈《〓※*†‡§¶"
)


def split_configured_symbols(value: str | None) -> tuple[str, ...]:
    """Parse a user-entered symbol inventory while preserving custom tokens.

    Continuous, space-separated and comma-separated known symbol strings are
    equivalent. A multi-character token is split only when every character is a
    known single-character marker; otherwise it is preserved as a custom literal.
    """
    text = str(value or "").strip()
    if not text:
        return ()
    import re

    raw_parts = [
        part for part in re.split(r"[\s,，、;；]+", text)
        if part
    ]
    result: list[str] = []
    for part in raw_parts:
        if len(part) > 1 and all(ch in KNOWN_SINGLE_MARKER_SYMBOLS for ch in part):
            result.extend(part)
        else:
            result.append(part)
    return tuple(dict.fromkeys(result))


def _otsu_threshold(gray: np.ndarray) -> int:
    values = np.asarray(gray, dtype=np.uint8).ravel()
    if values.size == 0:
        return 127
    hist = np.bincount(values, minlength=256).astype(np.float64)
    total = float(values.size)
    sum_total = float(np.dot(np.arange(256, dtype=np.float64), hist))
    sum_bg = 0.0
    weight_bg = 0.0
    best = 127
    best_var = -1.0
    for threshold in range(256):
        weight_bg += hist[threshold]
        if weight_bg <= 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg <= 0:
            break
        sum_bg += threshold * hist[threshold]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_total - sum_bg) / weight_fg
        between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if between > best_var:
            best_var = between
            best = threshold
    return int(best)


def _principal_component(mask: np.ndarray) -> np.ndarray:
    """Keep the dominant connected ink component from a user crop.

    Tight crops normally contain one marker. If nearby text leaks into the
    selection, retaining the dominant component prevents that text from becoming
    part of the reusable template.
    """
    ink = np.asarray(mask, dtype=bool)
    h, w = ink.shape
    seen = np.zeros_like(ink, dtype=bool)
    best: list[tuple[int, int]] = []
    for y in range(h):
        for x in range(w):
            if not ink[y, x] or seen[y, x]:
                continue
            component: list[tuple[int, int]] = []
            stack = [(y, x)]
            while stack:
                yy, xx = stack.pop()
                if not (0 <= yy < h and 0 <= xx < w):
                    continue
                if seen[yy, xx] or not ink[yy, xx]:
                    continue
                seen[yy, xx] = True
                component.append((yy, xx))
                stack.extend(
                    ((yy - 1, xx), (yy + 1, xx), (yy, xx - 1), (yy, xx + 1))
                )
            if len(component) > len(best):
                best = component
    if not best:
        return ink
    result = np.zeros_like(ink, dtype=bool)
    for y, x in best:
        result[y, x] = True
    return result


def _hole_count(mask: np.ndarray) -> int:
    """Count background components enclosed by ink on a normalized mask."""
    ink = np.asarray(mask, dtype=bool)
    if ink.ndim != 2 or ink.size == 0:
        return 0
    background = ~ink
    h, w = background.shape
    seen = np.zeros_like(background, dtype=bool)
    stack: list[tuple[int, int]] = []
    for x in range(w):
        if background[0, x]:
            stack.append((0, x))
        if background[h - 1, x]:
            stack.append((h - 1, x))
    for y in range(h):
        if background[y, 0]:
            stack.append((y, 0))
        if background[y, w - 1]:
            stack.append((y, w - 1))
    while stack:
        y, x = stack.pop()
        if not (0 <= y < h and 0 <= x < w):
            continue
        if seen[y, x] or not background[y, x]:
            continue
        seen[y, x] = True
        stack.extend(((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)))

    holes = 0
    for y in range(h):
        for x in range(w):
            if not background[y, x] or seen[y, x]:
                continue
            holes += 1
            stack = [(y, x)]
            while stack:
                yy, xx = stack.pop()
                if not (0 <= yy < h and 0 <= xx < w):
                    continue
                if seen[yy, xx] or not background[yy, xx]:
                    continue
                seen[yy, xx] = True
                stack.extend(
                    ((yy - 1, xx), (yy + 1, xx), (yy, xx - 1), (yy, xx + 1))
                )
    return holes


def _normalize_ink_mask(
    mask: np.ndarray, *, canvas_size: int = DEFAULT_TEMPLATE_SIZE
) -> dict[str, Any]:
    ink = np.asarray(mask, dtype=bool)
    if ink.ndim != 2 or ink.size == 0:
        raise ValueError("empty marker image")
    ys, xs = np.nonzero(ink)
    if xs.size < 3 or ys.size < 3:
        raise ValueError("marker selection contains too little ink")

    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    cropped = ink[y0:y1, x0:x1]
    source_h, source_w = cropped.shape
    aspect = float(source_w / max(1, source_h))

    size = max(16, min(64, int(canvas_size)))
    inner = max(8, size - 4)
    scale = min(inner / max(1, source_w), inner / max(1, source_h))
    target_w = max(1, round(source_w * scale))
    target_h = max(1, round(source_h * scale))
    image = Image.fromarray((cropped.astype(np.uint8) * 255), mode="L")
    resized = np.asarray(
        image.resize((target_w, target_h), Image.Resampling.NEAREST),
        dtype=np.uint8,
    ) >= 128
    canvas = np.zeros((size, size), dtype=bool)
    ox = (size - target_w) // 2
    oy = (size - target_h) // 2
    canvas[oy:oy + target_h, ox:ox + target_w] = resized

    margin = max(1, round(size * 0.31))
    central = canvas[margin:size - margin, margin:size - margin]
    density = float(canvas.mean())
    central_ink = float(central.mean()) if central.size else density
    bitmap = "".join("1" if value else "0" for value in canvas.ravel())
    return {
        "size": size,
        "bitmap": bitmap,
        "aspect_ratio": round(aspect, 5),
        "density": round(density, 5),
        "central_ink": round(central_ink, 5),
        "hole_count": int(_hole_count(canvas)),
    }


def trim_visual_marker_crop(
    image: Image.Image,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Remove surrounding white space using the same dominant-ink logic as templates.

    The returned box is relative to the input crop and can therefore be added
    to the original source selection to keep source_box truthful after trimming.
    """
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    if gray.size == 0:
        raise ValueError("empty marker crop")
    threshold = _otsu_threshold(gray)
    ink = _principal_component(gray <= threshold)
    ys, xs = np.nonzero(ink)
    if xs.size < 3 or ys.size < 3:
        raise ValueError("marker selection contains too little ink")
    left = int(xs.min())
    top = int(ys.min())
    right = int(xs.max()) + 1
    bottom = int(ys.max()) + 1
    return image.crop((left, top, right, bottom)), (left, top, right, bottom)

def normalize_visual_marker_crop(
    image: Image.Image, *, canvas_size: int = DEFAULT_TEMPLATE_SIZE
) -> dict[str, Any]:
    """Normalize a user-selected marker crop into a portable binary template."""
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    if gray.size == 0:
        raise ValueError("empty marker crop")
    threshold = _otsu_threshold(gray)
    ink = _principal_component(gray <= threshold)
    normalized = _normalize_ink_mask(ink, canvas_size=canvas_size)
    normalized["threshold"] = int(threshold)
    return normalized


def build_visual_marker_sample(
    image: Image.Image,
    *,
    role: str,
    literal: str = "",
    sample_id: str = "",
    source_page: str = "",
    source_box: Iterable[int] | None = None,
    canvas_size: int = DEFAULT_TEMPLATE_SIZE,
) -> dict[str, Any]:
    role = str(role or "").strip()
    if role not in VALID_TEMPLATE_ROLES:
        raise ValueError(f"unsupported marker role: {role}")
    normalized = normalize_visual_marker_crop(image, canvas_size=canvas_size)
    box = [int(value) for value in (source_box or [])]
    if box and len(box) != 4:
        raise ValueError("source_box must contain x0, y0, x1, y1")
    return {
        "id": str(sample_id or "").strip(),
        "role": role,
        "literal": str(literal or "").strip(),
        "source_page": str(source_page or ""),
        "source_box": box,
        **normalized,
    }


def _valid_sample(sample: Any) -> bool:
    if not isinstance(sample, dict):
        return False
    if str(sample.get("role") or "") not in VALID_TEMPLATE_ROLES:
        return False
    try:
        size = int(sample.get("size") or 0)
    except (TypeError, ValueError):
        return False
    bitmap = str(sample.get("bitmap") or "")
    return (
        16 <= size <= 64
        and len(bitmap) == size * size
        and set(bitmap).issubset({"0", "1"})
    )


def parse_visual_marker_samples(value: Any) -> list[dict[str, Any]]:
    """Read samples from settings JSON; malformed entries are ignored safely."""
    if value in (None, ""):
        return []
    payload: Any = value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if isinstance(payload, dict):
        payload = payload.get("samples", [])
    if not isinstance(payload, list):
        return []
    return [dict(sample) for sample in payload if _valid_sample(sample)]


def serialize_visual_marker_samples(samples: Iterable[dict[str, Any]]) -> str:
    valid = [dict(sample) for sample in samples if _valid_sample(sample)]
    return json.dumps(
        {"version": TEMPLATE_FORMAT_VERSION, "samples": valid},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def visual_marker_samples_from_settings(settings: Any) -> list[dict[str, Any]]:
    return parse_visual_marker_samples(
        getattr(settings, "profile_symbol_templates_json", "")
    )


def _sample_bitmap(sample: dict[str, Any]) -> np.ndarray:
    size = int(sample["size"])
    values = np.fromiter(
        (char == "1" for char in str(sample["bitmap"])),
        dtype=bool,
        count=size * size,
    )
    return values.reshape((size, size))


def _shifted_iou(left: np.ndarray, right: np.ndarray, max_shift: int = 2) -> float:
    if left.shape != right.shape:
        return 0.0
    h, w = left.shape
    best = 0.0
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            shifted = np.zeros_like(right)
            src_y0 = max(0, -dy)
            src_y1 = min(h, h - dy)
            src_x0 = max(0, -dx)
            src_x1 = min(w, w - dx)
            dst_y0 = max(0, dy)
            dst_y1 = dst_y0 + max(0, src_y1 - src_y0)
            dst_x0 = max(0, dx)
            dst_x1 = dst_x0 + max(0, src_x1 - src_x0)
            if src_y1 <= src_y0 or src_x1 <= src_x0:
                continue
            shifted[dst_y0:dst_y1, dst_x0:dst_x1] = right[
                src_y0:src_y1, src_x0:src_x1
            ]
            union = np.logical_or(left, shifted).sum()
            if union <= 0:
                continue
            score = float(np.logical_and(left, shifted).sum() / union)
            best = max(best, score)
    return best


def _projection_similarity(left: np.ndarray, right: np.ndarray) -> float:
    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom <= 1e-9:
            return 0.0
        return max(0.0, min(1.0, float(np.dot(a, b) / denom)))

    return 0.5 * (
        cosine(left.sum(axis=0).astype(float), right.sum(axis=0).astype(float))
        + cosine(left.sum(axis=1).astype(float), right.sum(axis=1).astype(float))
    )


def match_visual_marker_template(
    mask: np.ndarray,
    samples: Iterable[dict[str, Any]],
    *,
    roles: set[str] | None = None,
) -> dict[str, Any] | None:
    """Return the best dictionary-specific template match for one component."""
    sample_list = [
        sample for sample in samples
        if _valid_sample(sample)
        and (roles is None or str(sample.get("role") or "") in roles)
    ]
    if not sample_list:
        return None

    candidate = _normalize_ink_mask(mask, canvas_size=DEFAULT_TEMPLATE_SIZE)
    candidate_bitmap = _sample_bitmap(candidate)
    best: dict[str, Any] | None = None
    for sample in sample_list:
        sample_bitmap = _sample_bitmap(sample)
        if sample_bitmap.shape != candidate_bitmap.shape:
            sample_image = Image.fromarray(
                (sample_bitmap.astype(np.uint8) * 255), mode="L"
            ).resize(candidate_bitmap.shape[::-1], Image.Resampling.NEAREST)
            sample_bitmap = np.asarray(sample_image, dtype=np.uint8) >= 128

        iou = _shifted_iou(candidate_bitmap, sample_bitmap)
        projection = _projection_similarity(candidate_bitmap, sample_bitmap)
        density_similarity = max(
            0.0,
            1.0 - abs(
                float(candidate["density"]) - float(sample.get("density", 0.0))
            ) / 0.35,
        )
        candidate_aspect = max(1e-5, float(candidate["aspect_ratio"]))
        sample_aspect = max(1e-5, float(sample.get("aspect_ratio", 1.0) or 1.0))
        aspect_similarity = math.exp(
            -1.8 * abs(math.log(candidate_aspect / sample_aspect))
        )
        hole_similarity = (
            1.0
            if int(candidate["hole_count"]) == int(sample.get("hole_count", 0) or 0)
            else 0.35
        )
        score = (
            0.50 * iou
            + 0.20 * projection
            + 0.10 * density_similarity
            + 0.10 * aspect_similarity
            + 0.10 * hole_similarity
        )
        item = {
            "score": round(float(score), 5),
            "iou": round(float(iou), 5),
            "projection": round(float(projection), 5),
            "density_similarity": round(float(density_similarity), 5),
            "aspect_similarity": round(float(aspect_similarity), 5),
            "hole_similarity": round(float(hole_similarity), 5),
            "sample": dict(sample),
            "candidate": candidate,
        }
        if best is None or float(item["score"]) > float(best["score"]):
            best = item
    return best
