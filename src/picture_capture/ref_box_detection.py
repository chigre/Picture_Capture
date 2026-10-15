"""Local, opt-in whole-image template matching for REF rectangles.

Samples are cropped from the user's image into local project storage only.
No scan, sample, template, or OCR content is sent over the network.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import uuid

import numpy as np
from PIL import Image

from .image_utils import normalize_page_rgb

from .formats import pdic_path, read_pdic
from .page_sections import read_page_sections
from .ref_boxes import (
    RefBox, box_intersection_fraction, next_ref_id, read_ref_boxes,
    ref_box_ticket, ref_sample_root, write_ref_boxes,
)


def list_ref_samples(project_root: Path) -> list[Path]:
    folder = ref_sample_root(project_root)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.name.startswith("ref_sample_")
                  and p.suffix.lower() == ".png")


def add_ref_sample(image_path: Path, source_box: tuple[int, int, int, int]) -> Path:
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
) -> list[tuple[int, int, int, int]]:
    """Bounded multiscale RGB matching, with NumPy fallback if CV is missing.

    No blue-only rule, no network dependencies, no training, no image upload.
    """
    try:
        import cv2
    except ImportError:
        cv2 = None
    if not 0.60 <= float(threshold) <= 0.999:
        raise ValueError("REF match threshold must be between 0.60 and 0.999")
    # FFT fallback uses considerably more memory than OpenCV. A bounded
    # temporary view is sufficient for ordinary glyph-sized REF templates;
    # returned coordinates always refer to full-resolution source pixels.
    original_width, original_height = image.size
    ratio = (min(1.0, 2048 / max(original_width, original_height))
             if cv2 is None else 1.0)
    if ratio < 1.0:
        resized = image.convert("RGB").resize(
            (max(1, round(original_width * ratio)),
             max(1, round(original_height * ratio))), Image.Resampling.BILINEAR,
        )
        source = np.asarray(resized, dtype=np.uint8)
    else:
        source = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width = source.shape[:2]
    proposals: list[tuple[float, int, int, int, int]] = []
    for sample_path in samples:
        with Image.open(sample_path) as opened:
            source_template = np.asarray(opened.convert("RGB"), dtype=np.uint8)
        if min(source_template.shape[:2]) < 4 or float(source_template.std()) < 4.0:
            continue
        for factor in (0.85, 1.0, 1.15):
            sw = max(4, round(source_template.shape[1] * factor * ratio))
            sh = max(4, round(source_template.shape[0] * factor * ratio))
            if sw > width or sh > height:
                continue
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
                    max(1, round(sw / ratio)), max(1, round(sh / ratio)),
                ))
                pad_x, pad_y = max(1, round(sw * 0.65)), max(1, round(sh * 0.65))
                scores[max(0, yy-pad_y):min(scores.shape[0], yy+pad_y+1),
                       max(0, xx-pad_x):min(scores.shape[1], xx+pad_x+1)] = -1.0
    accepted: list[RefBox] = []
    for _, x, y, w, h in sorted(proposals, key=lambda row: (-row[0], row[2], row[1])):
        item = RefBox(len(accepted)+1, x, y, w, h, None)
        if any(box_intersection_fraction(item, other) > 0.25 for other in accepted):
            continue
        accepted.append(item)
        if len(accepted) >= max_results:
            break
    return [(p.x, p.y, p.w, p.h) for p in accepted]


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
        )
        entries = read_pdic(pdic_path(page))
        sections = read_page_sections(page)
        proposed = list(existing)
        for x, y, w, h in matches:
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
