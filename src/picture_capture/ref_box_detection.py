"""Local, opt-in whole-image template matching for REF rectangles.

Samples are cropped from the user's image into local project storage only.
No scan, sample, template, or OCR content is sent over the network.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import uuid

import numpy as np
from PIL import Image, ImageOps

from .image_utils import normalize_page_rgb

from .formats import pdic_path, read_pdic
from .page_sections import read_page_sections
from .ref_boxes import (
    RefBox, box_intersection_fraction, next_ref_id, read_ref_boxes,
    ref_box_ticket, ref_sample_root, write_ref_boxes,
)


REF_SAMPLE_CATEGORIES = ("见", "参见", "亦作", "同", "别名", "其他", "未分类")
REF_SAMPLE_DIRECTIONS = ("after", "before")


def default_ref_sample_direction(category: str) -> str:
    return "before" if category == "别名" else "after"


def _ref_sample_metadata_path(sample_path: Path) -> Path:
    return Path(sample_path).with_suffix(".json")


def read_ref_sample_metadata(sample_path: Path) -> dict[str, str]:
    """Legacy PNG templates remain valid, defaulting to after/未分类."""
    sidecar = _ref_sample_metadata_path(sample_path)
    if not sidecar.exists():
        return {"category": "未分类", "direction": "after"}
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"REF sample metadata must be an object: {sidecar.name}")
    category = str(payload.get("category") or "未分类").strip()
    direction = payload.get("direction", "after")
    if not category or len(category) > 40 or direction not in REF_SAMPLE_DIRECTIONS:
        raise ValueError(f"Invalid REF sample metadata: {sidecar.name}")
    return {"category": category, "direction": direction}


def write_ref_sample_metadata(
    sample_path: Path, *, category: str, direction: str,
) -> None:
    """Atomically save per-template category and before/after semantics."""
    category = str(category).strip()
    if not category or len(category) > 40:
        raise ValueError("REF sample category must have 1–40 characters")
    if direction not in REF_SAMPLE_DIRECTIONS:
        raise ValueError("REF sample direction must be after or before")
    target = _ref_sample_metadata_path(sample_path)
    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(json.dumps({"category": category, "direction": direction},
                                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def delete_ref_sample(sample_path: Path, project_root: Path) -> None:
    """Delete only a listed project-local PNG and its matching sidecar."""
    path = Path(sample_path)
    if path not in list_ref_samples(project_root):
        raise ValueError("REF sample is no longer in the project sample list")
    path.unlink()
    _ref_sample_metadata_path(path).unlink(missing_ok=True)


def list_ref_samples(project_root: Path) -> list[Path]:
    folder = ref_sample_root(project_root)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.name.startswith("ref_sample_")
                  and p.suffix.lower() == ".png")


def add_ref_sample(image_path: Path, source_box: tuple[int, int, int, int], *,
                   category: str = "未分类", direction: str = "after") -> Path:
    """Store only an explicitly user-selected rectangle; never a full scan."""
    page = Path(image_path)
    with Image.open(page) as opened:
        source = normalize_page_rgb(opened)
        x0, y0, x1, y1 = map(int, source_box)
        if not (0 <= x0 < x1 <= source.width and 0 <= y0 < y1 <= source.height):
            raise ValueError("REF template selection exceeds the page")
        if x1 - x0 < 4 or y1 - y0 < 4:
            raise ValueError("REF template crop is too small")
        sample = source.crop((x0, y0, x1, y1))
    target_dir = ref_sample_root(page.parent)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"ref_sample_{uuid.uuid4().hex}.png"
    temp = target_dir / f".{target.stem}.tmp"
    try:
        sample.save(temp, format="PNG")
        temp.replace(target)
        try:
            write_ref_sample_metadata(target, category=category, direction=direction)
        except Exception:
            target.unlink(missing_ok=True)
            raise
    finally:
        sample.close()
        temp.unlink(missing_ok=True)
    return target


def _numpy_template_scores(source: np.ndarray, template: np.ndarray) -> np.ndarray:
    """RGB-normalized cross-correlation with NumPy FFT; no optional CV dependency.

    Per-channel mean subtraction is the TM_CCOEFF_NORMED convention. The
    image is bounded by the caller to avoid memory spikes on large scans.
    """
    height, width = source.shape[:2]
    th, tw = template.shape[:2]
    if source.ndim == 2:
        source = source[..., None]
    if template.ndim == 2:
        template = template[..., None]
    if th > height or tw > width:
        return np.empty((0, 0), dtype=np.float32)
    hfft, wfft = height + th - 1, width + tw - 1
    channel_count = source.shape[2]
    kernel = template.astype(np.float32)
    kernel -= kernel.mean(axis=(0, 1), keepdims=True)
    k_norm = float(np.square(kernel).sum())
    if k_norm < 1e-6:
        return np.full((height-th+1, width-tw+1), -1.0, dtype=np.float32)
    numerator = np.zeros((height-th+1, width-tw+1), dtype=np.float64)
    window_variance = np.zeros_like(numerator)
    window_area = th * tw
    for channel in range(channel_count):
        array = source[:, :, channel].astype(np.float32)
        kernel_channel = kernel[::-1, ::-1, channel]
        spectrum = np.fft.rfft2(array, s=(hfft, wfft))
        spectrum *= np.fft.rfft2(kernel_channel, s=(hfft, wfft))
        correlation = np.fft.irfft2(spectrum, s=(hfft, wfft))
        numerator += correlation[th - 1:height, tw - 1:width]
        square = array.astype(np.float64)
        integral = np.pad(square, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
        integral2 = np.pad(square * square, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
        totals = (integral[th:, tw:] - integral[:-th, tw:]
                  - integral[th:, :-tw] + integral[:-th, :-tw])
        totals2 = (integral2[th:, tw:] - integral2[:-th, tw:]
                   - integral2[th:, :-tw] + integral2[:-th, :-tw])
        window_variance += np.maximum(0.0, totals2 - totals * totals / window_area)
    denom = np.sqrt(np.maximum(1e-8, k_norm * window_variance))
    score = np.clip(numerator / denom, -1.0, 1.0).astype(np.float32)
    score[window_variance < 1e-5] = -1.0
    return score


def match_ref_templates(
    image: Image.Image, samples: list[Path], *,
    threshold: float = 0.88, max_results: int = 200,
    scale_tolerance_percent: float = 25.0,
    with_sources: bool = False,
) -> list:
    """Bounded multiscale contrast-normalized grayscale guide-word matching.

    Color/brightness differences are normalized without clipping rare guide
    ink pixels: whole-page percentile cutoff can destroy a small sample.
    Search over
    multiple template scales for cross-page resolution and mild print-size
    differences. Localized nonlinear page warp remains a limitation; do not
    claim OCR or geometric rectification. NumPy fallback requires no cv2.
    """
    try:
        import cv2
    except ImportError:
        cv2 = None
    if not 0.60 <= float(threshold) <= 0.999:
        raise ValueError("REF match threshold must be between 0.60 and 0.999")
    if not 0 <= float(scale_tolerance_percent) <= 50:
        raise ValueError("REF scale tolerance must be between 0 and 50 percent")
    # FFT fallback uses considerably more memory than OpenCV. A bounded
    # temporary view is sufficient for ordinary glyph-sized REF templates;
    # returned coordinates always refer to full-resolution source pixels.
    original_width, original_height = image.size
    ratio = (min(1.0, 2048 / max(original_width, original_height))
             if cv2 is None else 1.0)
    if ratio < 1.0:
        resized = ImageOps.grayscale(image).resize(
            (max(1, round(original_width * ratio)),
             max(1, round(original_height * ratio))), Image.Resampling.BILINEAR,
        )
        source = np.asarray(ImageOps.autocontrast(resized, cutoff=0), dtype=np.uint8)
    else:
        source = np.asarray(
            ImageOps.autocontrast(ImageOps.grayscale(image), cutoff=0),
            dtype=np.uint8,
        )
    height, width = source.shape[:2]
    proposals: list[tuple[float, int, int, int, int, Path]] = []
    scale_tolerance = float(scale_tolerance_percent) / 100.0
    factors = tuple(np.linspace(
        1.0 - scale_tolerance, 1.0 + scale_tolerance,
        7 if scale_tolerance > 0 else 1,
    ))
    # Curved pages can locally stretch text differently in X and Y.
    # Two bounded aspect-ratio variants complement the isotropic scales;
    # these are NOT a nonlinear dewarp or OCR substitute.
    scales = [(float(f), float(f)) for f in factors]
    if scale_tolerance > 0:
        aspect = min(0.08, scale_tolerance)
        scales.extend(((1 + aspect, 1 - aspect),
                       (1 - aspect, 1 + aspect)))
    for sample_path in samples:
        with Image.open(sample_path) as opened:
            source_template = np.asarray(
                ImageOps.autocontrast(ImageOps.grayscale(opened), cutoff=0),
                dtype=np.uint8,
            )
        if min(source_template.shape[:2]) < 4 or float(source_template.std()) < 4.0:
            continue
        used_sizes: set[tuple[int, int]] = set()
        for width_factor, height_factor in scales:
            sw = max(4, round(source_template.shape[1] * width_factor * ratio))
            sh = max(4, round(source_template.shape[0] * height_factor * ratio))
            if (sw, sh) in used_sizes or sw > width or sh > height:
                continue
            used_sizes.add((sw, sh))
            if cv2 is not None:
                template = cv2.resize(source_template, (sw, sh), interpolation=cv2.INTER_AREA)
            else:
                template = np.asarray(
                    Image.fromarray(source_template).resize(
                        (sw, sh), Image.Resampling.BILINEAR,
                    ), dtype=np.uint8,
                )
            if template.std() < 4.0:
                continue
            scores = (
                cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED)
                if cv2 is not None else _numpy_template_scores(source, template)
            )
            # Suppress peaks without materializing every matching pixel.
            for _ in range(max_results):
                if cv2 is not None:
                    _, score, _, (xx, yy) = cv2.minMaxLoc(scores)
                else:
                    flat = int(np.argmax(scores))
                    yy, xx = np.unravel_index(flat, scores.shape)
                    score = float(scores[yy, xx])
                if not np.isfinite(score) or score < threshold:
                    break
                proposals.append((
                    float(score), round(xx / ratio), round(yy / ratio),
                    max(1, round(sw / ratio)), max(1, round(sh / ratio)), sample_path,
                ))
                pad_x, pad_y = max(1, round(sw * 0.65)), max(1, round(sh * 0.65))
                scores[max(0, yy-pad_y):min(scores.shape[0], yy+pad_y+1),
                       max(0, xx-pad_x):min(scores.shape[1], xx+pad_x+1)] = -1.0
    accepted: list[RefBox] = []
    accepted_sources: list[Path] = []
    for _, x, y, w, h, source_path in sorted(proposals, key=lambda row: (-row[0], row[2], row[1])):
        item = RefBox(len(accepted)+1, x, y, w, h, None)
        if any(box_intersection_fraction(item, other) > 0.25 for other in accepted):
            continue
        accepted.append(item)
        accepted_sources.append(source_path)
        if len(accepted) >= max_results:
            break
    guides = [(p.x, p.y, p.w, p.h) for p in accepted]
    return list(zip(guides, accepted_sources)) if with_sources else guides


def default_ref_box_dimensions(settings) -> tuple[int, int]:
    """Same size rule for manual single-click and auto-detected REF boxes."""
    line_height = max(
        2.0,
        float(getattr(settings, "character_height", 26))
        + float(getattr(settings, "row_padding", 0)),
    )
    width = max(2, round(
        line_height * float(getattr(settings, "ref_box_width_lines", 2)),
    ))
    height = max(2, round(
        line_height * float(getattr(settings, "ref_box_height_lines", 1)),
    ))
    return width, height


def ref_box_after_guide(
    guide: tuple[int, int, int, int],
    image_size: tuple[int, int],
    settings,
    direction: str = "after",
) -> tuple[int, int, int, int] | None:
    """Position REF before/after its guide, optionally including the guide.

    REF default width always measures the non-guide region. When enabled,
    the matching template (using its actual matched/scaled width) is included
    in the target; all positions are clamped to the source image.
    """
    x, y, guide_w, guide_h = guide
    page_w, page_h = image_size
    if direction not in REF_SAMPLE_DIRECTIONS:
        raise ValueError(f"Invalid REF template direction: {direction}")
    ref_w, ref_h = default_ref_box_dimensions(settings)
    # Do not create guide-only REF boxes if the intended text side is absent.
    if ((direction == "after" and x + guide_w + 2 > page_w)
            or (direction == "before" and x < 2)):
        return None
    include_guide = bool(getattr(settings, "ref_box_include_guide_width", False))
    target_start = (x + guide_w if direction == "after" else x - ref_w)
    target_end = (x + guide_w + ref_w if direction == "after" else x)
    if include_guide:
        target_start = min(target_start, x)
        target_end = max(target_end, x + guide_w)
    target_start = max(0, target_start)
    target_end = min(page_w, target_end)
    if target_end - target_start < 2 or page_h < 2:
        return None
    target_h = min(ref_h, page_h)
    target_y = max(0, min(page_h - target_h,
                           round(y + (guide_h - target_h) / 2)))
    return target_start, target_y, target_end - target_start, target_h

def associate_ref_to_entry(
    image: Image.Image, entries: list, settings, page_index: int,
    sections, x: int, y: int, w: int, h: int,
) -> int | None:
    """Use the same SECTION/column/entry crop travel as word export.

    A REF inside an unowned previous-page continuation remains unlinked.
    """
    if not entries:
        return None
    from .processing_core import _base_entry_crop_pieces
    _ordered, pieces = _base_entry_crop_pieces(
        image, entries, settings, profile_page_index=page_index,
        page_sections=sections,
    )
    cx, cy = x + w / 2, y + h / 2
    matches = [
        p for p in pieces
        if p.entry_ref_index is not None and
        p.box[0] <= cx < p.box[2] and p.box[1] <= cy < p.box[3]
    ]
    if not matches:
        return None
    return matches[0].entry_ref_index


def detect_ref_boxes_page(image_path: Path, settings, page_index: int) -> dict:
    """Add non-overlapping REF matches, preserving every existing REF record."""
    page = Path(image_path)
    ticket = ref_box_ticket(page)
    existing = read_ref_boxes(page)
    samples = list_ref_samples(page.parent)
    if not samples:
        return {"status": "skipped_no_samples", "page": page.name, "added": 0}
    with Image.open(page) as opened:
        image = normalize_page_rgb(opened)
    try:
        matches = match_ref_templates(
            image, samples,
            threshold=float(getattr(settings, "ref_match_threshold", 0.88)),
            scale_tolerance_percent=float(getattr(
                settings, "ref_match_scale_tolerance_percent", 25.0,
            )),
            with_sources=True,
        )
        entries = read_pdic(pdic_path(page))
        sections = read_page_sections(page)
        proposed = list(existing)
        metadata_cache: dict[Path, dict[str, str]] = {}
        for guide, sample_path in matches:
            if sample_path not in metadata_cache:
                metadata_cache[sample_path] = read_ref_sample_metadata(sample_path)
            target = ref_box_after_guide(
                guide, image.size, settings,
                direction=metadata_cache[sample_path]["direction"],
            )
            if target is None:
                continue
            x, y, w, h = target
            placeholder = RefBox(1, x, y, w, h, None)
            if any(box_intersection_fraction(placeholder, old) > 0.15 for old in proposed):
                continue
            ordinal = associate_ref_to_entry(
                image, entries, settings, page_index, sections, x, y, w, h,
            )
            proposed.append(RefBox(next_ref_id(proposed), x, y, w, h, ordinal, ""))
    finally:
        image.close()
    added = len(proposed) - len(existing)
    if added:
        write_ref_boxes(page, proposed, expected_ticket=ticket)
    return {"status": "changed" if added else "unchanged", "page": page.name, "added": added}


def detect_ref_boxes_job(image_path: str, settings, page_index: int) -> dict:
    try:
        return detect_ref_boxes_page(Path(image_path), settings, page_index)
    except Exception as exc:
        return {"status": "failed", "page": Path(image_path).name,
                "error": f"{type(exc).__name__}: {exc}", "added": 0}
