from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .image_utils import normalize_page_rgb
from .layout_detection import analysis_ink_mask, detect_text_polygons
from .models import AppSettings
from .project_storage import image_preprocess_data_root, image_preprocess_output_root


PREPROCESS_FORMAT = "picture-capture-image-preprocess"
PREPROCESS_FORMAT_VERSION = 1
DEFAULT_SAFETY_MARGIN_PERCENT = 1.5
DEFAULT_MAX_AUTO_DESKEW_DEG = 5.0
DEFAULT_DESKEW_DEAD_ZONE_DEG = 0.12
PREVIEW_YELLOW = (255, 225, 110, 94)
PREVIEW_OUTLINE = (218, 164, 24, 255)


@dataclass(slots=True)
class PreprocessAnalysis:
    source_width: int
    source_height: int
    correction_angle_deg: float
    applied_angle_deg: float
    crop_box: tuple[int, int, int, int]
    raw_content_box: tuple[int, int, int, int]
    text_box: tuple[int, int, int, int] | None
    source_boxes: int
    angle_samples: int
    angle_mad_deg: float
    retained_ratio: float
    confidence: float
    status: str
    method: str
    warnings: tuple[str, ...] = ()
    safety_margin_percent: float = DEFAULT_SAFETY_MARGIN_PERCENT
    source_size_bytes: int = 0
    source_mtime_ns: int = 0

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["format"] = PREPROCESS_FORMAT
        payload["format_version"] = PREPROCESS_FORMAT_VERSION
        payload["crop_box"] = list(self.crop_box)
        payload["raw_content_box"] = list(self.raw_content_box)
        payload["text_box"] = list(self.text_box) if self.text_box is not None else None
        payload["warnings"] = list(self.warnings)
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "PreprocessAnalysis":
        if not isinstance(payload, dict):
            raise ValueError("图片预处理结果格式无效")
        crop = tuple(int(v) for v in payload.get("crop_box", ()))
        raw = tuple(int(v) for v in payload.get("raw_content_box", ()))
        text = payload.get("text_box")
        text_box = tuple(int(v) for v in text) if isinstance(text, (list, tuple)) and len(text) == 4 else None
        if len(crop) != 4 or len(raw) != 4:
            raise ValueError("图片预处理结果缺少裁剪坐标")
        return cls(
            source_width=max(1, int(payload.get("source_width", 1))),
            source_height=max(1, int(payload.get("source_height", 1))),
            correction_angle_deg=float(payload.get("correction_angle_deg", 0.0)),
            applied_angle_deg=float(payload.get("applied_angle_deg", 0.0)),
            crop_box=crop,  # type: ignore[arg-type]
            raw_content_box=raw,  # type: ignore[arg-type]
            text_box=text_box,  # type: ignore[arg-type]
            source_boxes=max(0, int(payload.get("source_boxes", 0))),
            angle_samples=max(0, int(payload.get("angle_samples", 0))),
            angle_mad_deg=max(0.0, float(payload.get("angle_mad_deg", 0.0))),
            retained_ratio=max(0.0, min(1.0, float(payload.get("retained_ratio", 1.0)))),
            confidence=max(0.0, min(1.0, float(payload.get("confidence", 0.0)))),
            status=str(payload.get("status", "review") or "review"),
            method=str(payload.get("method", "unknown") or "unknown"),
            warnings=tuple(str(item) for item in payload.get("warnings", ()) if str(item).strip()),
            safety_margin_percent=max(
                0.0, float(payload.get("safety_margin_percent", DEFAULT_SAFETY_MARGIN_PERCENT))
            ),
            source_size_bytes=max(0, int(payload.get("source_size_bytes", 0))),
            source_mtime_ns=max(0, int(payload.get("source_mtime_ns", 0))),
        )


def _normalize_half_turn(angle: float) -> float:
    value = float(angle)
    while value >= 90.0:
        value -= 180.0
    while value < -90.0:
        value += 180.0
    return value


def _weighted_median(values: list[tuple[float, float]]) -> float:
    if not values:
        return 0.0
    ordered = sorted((float(value), max(0.0, float(weight))) for value, weight in values)
    total = sum(weight for _value, weight in ordered)
    if total <= 0:
        return float(np.median([value for value, _weight in ordered]))
    halfway = total / 2.0
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= halfway:
            return value
    return ordered[-1][0]


def estimate_skew_from_polygons(
    polygons: Iterable[np.ndarray], *, writing_mode: str = "horizontal-tb",
) -> tuple[float, int, float]:
    """Estimate the small correction angle represented by detected text boxes.

    Angles use Pillow's rotation sign convention: a positive value is the
    counter-clockwise correction that should be applied to the source image.
    """
    vertical = str(writing_mode or "horizontal-tb").startswith("vertical")
    samples: list[tuple[float, float]] = []
    for raw in polygons:
        poly = np.asarray(raw, dtype=float)
        if poly.ndim != 2 or poly.shape[0] < 3 or poly.shape[1] < 2:
            continue
        edges: list[tuple[float, float]] = []
        for index in range(poly.shape[0]):
            p0 = poly[index, :2]
            p1 = poly[(index + 1) % poly.shape[0], :2]
            dx = float(p1[0] - p0[0])
            dy = float(p1[1] - p0[1])
            length = math.hypot(dx, dy)
            if length < 6.0:
                continue
            angle = _normalize_half_turn(math.degrees(math.atan2(dy, dx)))
            deviation = _normalize_half_turn(angle - 90.0) if vertical else angle
            if abs(deviation) <= 20.0:
                edges.append((deviation, length))
        if not edges:
            continue
        # Two long parallel sides carry most of the orientation information and
        # avoid over-weighting irregular multi-point detector polygons.
        for deviation, length in sorted(edges, key=lambda item: item[1], reverse=True)[:2]:
            samples.append((deviation, length))

    if not samples:
        return 0.0, 0, 0.0
    center = _weighted_median(samples)
    mad = _weighted_median([(abs(value - center), weight) for value, weight in samples])
    kept = [(value, weight) for value, weight in samples if abs(value - center) <= max(0.35, mad * 3.5)]
    if len(kept) >= 4:
        center = _weighted_median(kept)
        mad = _weighted_median([(abs(value - center), weight) for value, weight in kept])
        samples = kept
    return float(center), len(samples), float(mad)


def _smooth_1d(values: np.ndarray, width: int) -> np.ndarray:
    width = max(1, int(width))
    if width <= 1:
        return values.astype(float, copy=False)
    kernel = np.ones(width, dtype=float) / float(width)
    return np.convolve(values.astype(float, copy=False), kernel, mode="same")


def _projection_content_box(image: Image.Image, settings: AppSettings) -> tuple[int, int, int, int]:
    """Find a conservative nonblank content envelope without OCR recognition."""
    source = normalize_page_rgb(image)
    scale = min(1.0, 1800.0 / max(1, max(source.size)))
    work = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.BILINEAR,
    ) if scale < 1.0 else source
    gray = np.asarray(ImageOps.grayscale(work), dtype=np.uint8)
    ink = analysis_ink_mask(gray, settings).copy()
    h, w = ink.shape

    # Scanner shadows and cut marks commonly live on the physical edge.  Ignore
    # only a very narrow rim; meaningful page content is recovered below by the
    # Paddle text envelope and the user-facing safety margin.
    mx = max(1, round(w * 0.005))
    my = max(1, round(h * 0.005))
    ink[:my, :] = False
    ink[-my:, :] = False
    ink[:, :mx] = False
    ink[:, -mx:] = False

    rows = _smooth_1d(ink.mean(axis=1), max(3, round(h * 0.0015)))
    cols = _smooth_1d(ink.mean(axis=0), max(3, round(w * 0.0025)))
    positive_rows = rows[rows > 0]
    positive_cols = cols[cols > 0]
    row_floor = (
        max(0.0015, float(np.percentile(positive_rows, 15)) * 0.35)
        if positive_rows.size else 0.0015
    )
    col_floor = (
        max(0.0015, float(np.percentile(positive_cols, 15)) * 0.35)
        if positive_cols.size else 0.0015
    )
    active_y = np.flatnonzero(rows > row_floor)
    active_x = np.flatnonzero(cols > col_floor)
    if not active_y.size or not active_x.size:
        raise RuntimeError("未检测到足够的页面墨迹，无法估计保留区域。")

    back = 1.0 / max(scale, 1e-9)
    return (
        max(0, round(int(active_x[0]) * back)),
        max(0, round(int(active_y[0]) * back)),
        min(source.width, round(int(active_x[-1] + 1) * back)),
        min(source.height, round(int(active_y[-1] + 1) * back)),
    )


def _paper_fill(image: Image.Image) -> tuple[int, int, int]:
    source = normalize_page_rgb(image)
    w, h = source.size
    pw = max(1, round(w * 0.04))
    ph = max(1, round(h * 0.04))
    samples = [
        np.asarray(source.crop((0, 0, pw, ph)), dtype=np.uint8).reshape(-1, 3),
        np.asarray(source.crop((max(0, w - pw), 0, w, ph)), dtype=np.uint8).reshape(-1, 3),
        np.asarray(source.crop((0, max(0, h - ph), pw, h)), dtype=np.uint8).reshape(-1, 3),
        np.asarray(source.crop((max(0, w - pw), max(0, h - ph), w, h)), dtype=np.uint8).reshape(-1, 3),
    ]
    pixels = np.concatenate(samples, axis=0)
    median = np.median(pixels, axis=0)
    return tuple(int(round(value)) for value in median[:3])


def deskew_image(image: Image.Image, correction_angle_deg: float) -> Image.Image:
    source = normalize_page_rgb(image)
    angle = float(correction_angle_deg)
    if abs(angle) < 1e-6:
        return source.copy()
    return source.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        expand=False,
        fillcolor=_paper_fill(source),
    )


def _rotate_point_same_canvas(
    x: float, y: float, width: int, height: int, angle_deg: float,
) -> tuple[float, float]:
    """Map a source point through Pillow-style positive CCW rotation, expand=False."""
    if abs(float(angle_deg)) < 1e-9:
        return float(x), float(y)
    cx = (float(width) - 1.0) / 2.0
    cy = (float(height) - 1.0) / 2.0
    dx = float(x) - cx
    dy = float(y) - cy
    radians = math.radians(float(angle_deg))
    cos_a = math.cos(radians)
    sin_a = math.sin(radians)
    return (
        cx + dx * cos_a + dy * sin_a,
        cy - dx * sin_a + dy * cos_a,
    )


def _rotated_text_box(
    polygons: Iterable[np.ndarray], width: int, height: int, angle_deg: float,
) -> tuple[int, int, int, int] | None:
    points: list[tuple[float, float]] = []
    for raw in polygons:
        poly = np.asarray(raw, dtype=float)
        if poly.ndim != 2 or poly.shape[0] < 3 or poly.shape[1] < 2:
            continue
        xs = poly[:, 0]
        ys = poly[:, 1]
        if float(xs.max() - xs.min()) < 3.0 or float(ys.max() - ys.min()) < 3.0:
            continue
        for x, y in poly[:, :2]:
            points.append(_rotate_point_same_canvas(float(x), float(y), width, height, angle_deg))
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (
        max(0, min(width - 1, math.floor(min(xs)))),
        max(0, min(height - 1, math.floor(min(ys)))),
        max(1, min(width, math.ceil(max(xs)) + 1)),
        max(1, min(height, math.ceil(max(ys)) + 1)),
    )


def _merge_projection_and_text(
    projection: tuple[int, int, int, int],
    text_box: tuple[int, int, int, int] | None,
    width: int,
    height: int,
) -> tuple[tuple[int, int, int, int], bool]:
    if text_box is None:
        return projection, False
    px0, py0, px1, py1 = projection
    tx0, ty0, tx1, ty1 = text_box
    x0 = min(px0, tx0)
    y0 = min(py0, ty0)
    x1 = max(px1, tx1)
    y1 = max(py1, ty1)
    disagreement = False

    # If only the ink projection reaches the extreme physical edge while Paddle
    # sees text safely inside the page, treat it as scanner/binding noise and
    # retain a small context strip instead of the entire artifact.
    context_x = max(8, round(width * 0.018))
    context_y = max(8, round(height * 0.012))
    if px0 < width * 0.02 and tx0 > width * 0.04:
        x0 = max(px0, tx0 - context_x)
        disagreement = True
    if px1 > width * 0.98 and tx1 < width * 0.96:
        x1 = min(px1, tx1 + context_x)
        disagreement = True
    if py0 < height * 0.012 and ty0 > height * 0.035:
        y0 = max(py0, ty0 - context_y)
        disagreement = True
    if py1 > height * 0.988 and ty1 < height * 0.965:
        y1 = min(py1, ty1 + context_y)
        disagreement = True

    return (
        max(0, int(x0)), max(0, int(y0)),
        min(width, int(x1)), min(height, int(y1)),
    ), disagreement


def _median_polygon_height(polygons: Iterable[np.ndarray]) -> float:
    values: list[float] = []
    for raw in polygons:
        poly = np.asarray(raw, dtype=float)
        if poly.ndim != 2 or poly.shape[0] < 3 or poly.shape[1] < 2:
            continue
        height = float(poly[:, 1].max() - poly[:, 1].min())
        if 3.0 <= height:
            values.append(height)
    return float(np.median(values)) if values else 0.0


def _expand_box(
    box: tuple[int, int, int, int],
    width: int,
    height: int,
    *,
    safety_margin_percent: float,
    text_height: float,
) -> tuple[int, int, int, int]:
    percent = max(0.0, min(12.0, float(safety_margin_percent)))
    margin_x = max(round(width * percent / 100.0), round(text_height * 1.6))
    margin_y = max(round(height * percent / 100.0), round(text_height * 2.0))
    x0, y0, x1, y1 = box
    return (
        max(0, x0 - margin_x),
        max(0, y0 - margin_y),
        min(width, x1 + margin_x),
        min(height, y1 + margin_y),
    )


def _projection_skew_fallback(
    image: Image.Image, settings: AppSettings, *, writing_mode: str,
) -> float:
    """Slow but dependency-free skew fallback used only when Paddle gives no boxes."""
    source = normalize_page_rgb(image)
    scale = min(1.0, 1000.0 / max(1, max(source.size)))
    work = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.BILINEAR,
    ) if scale < 1.0 else source
    gray = np.asarray(ImageOps.grayscale(work), dtype=np.uint8)
    ink = analysis_ink_mask(gray, settings).astype(np.uint8) * 255
    mask = Image.fromarray(ink, mode="L")
    vertical = str(writing_mode or "horizontal-tb").startswith("vertical")

    def score(angle: float) -> float:
        rotated = mask.rotate(
            angle, resample=Image.Resampling.NEAREST, expand=False, fillcolor=0
        )
        array = np.asarray(rotated, dtype=np.float32) / 255.0
        projection = array.sum(axis=0 if vertical else 1)
        return float(np.square(np.diff(projection)).sum())

    coarse = [step * 0.25 for step in range(-10, 11)]
    coarse_scores = [score(angle) for angle in coarse]
    best = coarse[int(np.argmax(coarse_scores))]
    fine = [best - 0.25 + step * 0.05 for step in range(11)]
    fine_scores = [score(angle) for angle in fine]
    return float(fine[int(np.argmax(fine_scores))])


def analyze_preprocess_page(
    image: Image.Image,
    settings: AppSettings,
    *,
    safety_margin_percent: float = DEFAULT_SAFETY_MARGIN_PERCENT,
    auto_deskew: bool = True,
) -> PreprocessAnalysis:
    source = normalize_page_rgb(image)
    width, height = source.size
    warnings: list[str] = []
    polygons: list[np.ndarray] = []
    method = "paddle_text_polygons"

    try:
        polygons = detect_text_polygons(source, settings)
    except Exception as exc:
        method = "projection_fallback"
        warnings.append(f"Paddle文本检测不可用，已使用投影回退：{exc}")

    correction, angle_samples, angle_mad = estimate_skew_from_polygons(
        polygons, writing_mode=settings.layout_writing_mode,
    )
    if angle_samples < 4:
        method = "projection_fallback" if not polygons else "paddle+projection_angle"
        try:
            correction = _projection_skew_fallback(
                source, settings, writing_mode=settings.layout_writing_mode,
            )
            warnings.append("文本框角度样本较少，倾斜角由投影法补充估计。")
        except Exception as exc:
            correction = 0.0
            warnings.append(f"倾斜角回退估计失败：{exc}")

    if abs(correction) < DEFAULT_DESKEW_DEAD_ZONE_DEG:
        applied = 0.0
    elif abs(correction) <= DEFAULT_MAX_AUTO_DESKEW_DEG and auto_deskew:
        applied = float(correction)
    else:
        applied = 0.0
        if auto_deskew and abs(correction) > DEFAULT_MAX_AUTO_DESKEW_DEG:
            warnings.append(
                f"检测倾斜 {correction:+.2f}° 超过第一版自动纠偏上限 "
                f"{DEFAULT_MAX_AUTO_DESKEW_DEG:.1f}°，未自动旋转。"
            )

    corrected = deskew_image(source, applied)
    projection_box = _projection_content_box(corrected, settings)
    text_box = _rotated_text_box(polygons, width, height, applied)
    raw_content_box, boundary_disagreement = _merge_projection_and_text(
        projection_box, text_box, width, height,
    )
    if boundary_disagreement:
        warnings.append("页边墨迹与文本检测范围差异较大，已优先抑制极边缘扫描/装订痕迹。")

    text_height = _median_polygon_height(polygons)
    crop_box = _expand_box(
        raw_content_box, width, height,
        safety_margin_percent=safety_margin_percent,
        text_height=text_height,
    )
    x0, y0, x1, y1 = crop_box
    retained_ratio = max(0.0, min(1.0, ((x1 - x0) * (y1 - y0)) / float(width * height)))

    if angle_samples and angle_mad > 0.65:
        warnings.append(f"文本框倾斜角离散较大（MAD {angle_mad:.2f}°）。")
    if abs(correction) > 3.0:
        warnings.append(f"页面倾斜较大（{correction:+.2f}°），建议人工确认。")
    if len(polygons) < 8:
        warnings.append(f"有效文本框仅 {len(polygons)} 个，建议人工确认裁边。")
    if retained_ratio < 0.55:
        warnings.append(f"仅保留页面 {retained_ratio * 100:.1f}% 面积，裁剪幅度较大。")
    if retained_ratio > 0.975:
        warnings.append(f"保留页面 {retained_ratio * 100:.1f}% 面积，几乎未裁边。")

    confidence = min(1.0, len(polygons) / 45.0)
    if angle_samples:
        confidence *= max(0.25, 1.0 - min(1.0, angle_mad / 1.5))
    else:
        confidence *= 0.45
    if boundary_disagreement:
        confidence *= 0.85
    confidence = max(0.0, min(1.0, confidence))
    status = "review" if warnings or confidence < 0.45 else "normal"

    return PreprocessAnalysis(
        source_width=width,
        source_height=height,
        correction_angle_deg=round(float(correction), 4),
        applied_angle_deg=round(float(applied), 4),
        crop_box=crop_box,
        raw_content_box=raw_content_box,
        text_box=text_box,
        source_boxes=len(polygons),
        angle_samples=angle_samples,
        angle_mad_deg=round(float(angle_mad), 4),
        retained_ratio=retained_ratio,
        confidence=confidence,
        status=status,
        method=method,
        warnings=tuple(warnings),
        safety_margin_percent=float(safety_margin_percent),
    )


def analyze_preprocess_path(
    path: Path,
    settings: AppSettings,
    *,
    safety_margin_percent: float = DEFAULT_SAFETY_MARGIN_PERCENT,
    auto_deskew: bool = True,
) -> PreprocessAnalysis:
    path = Path(path)
    with Image.open(path) as opened:
        analysis = analyze_preprocess_page(
            opened,
            settings,
            safety_margin_percent=safety_margin_percent,
            auto_deskew=auto_deskew,
        )
    try:
        stat = path.stat()
        analysis.source_size_bytes = int(stat.st_size)
        analysis.source_mtime_ns = int(stat.st_mtime_ns)
    except OSError:
        pass
    return analysis


def result_path(project_root: Path, page: Path) -> Path:
    root = image_preprocess_data_root(project_root)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{Path(page).stem}.json"


def save_analysis(project_root: Path, page: Path, analysis: PreprocessAnalysis) -> Path:
    path = result_path(project_root, page)
    payload = analysis.to_dict()
    payload["page"] = Path(page).name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def load_analysis(project_root: Path, page: Path) -> PreprocessAnalysis | None:
    path = result_path(project_root, page)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return PreprocessAnalysis.from_dict(payload)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def analysis_is_current(
    analysis: PreprocessAnalysis,
    page: Path,
    *,
    safety_margin_percent: float,
) -> bool:
    page = Path(page)
    if abs(float(analysis.safety_margin_percent) - float(safety_margin_percent)) > 1e-6:
        return False
    try:
        stat = page.stat()
    except OSError:
        return False
    if analysis.source_size_bytes and int(stat.st_size) != int(analysis.source_size_bytes):
        return False
    if analysis.source_mtime_ns and int(stat.st_mtime_ns) != int(analysis.source_mtime_ns):
        return False
    return True


def overlay_excluded_regions(
    image: Image.Image,
    crop_box: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int, int] = PREVIEW_YELLOW,
    outline: tuple[int, int, int, int] = PREVIEW_OUTLINE,
) -> Image.Image:
    base = normalize_page_rgb(image).convert("RGBA")
    width, height = base.size
    x0, y0, x1, y1 = (
        max(0, min(width, int(crop_box[0]))),
        max(0, min(height, int(crop_box[1]))),
        max(0, min(width, int(crop_box[2]))),
        max(0, min(height, int(crop_box[3]))),
    )
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    if y0 > 0:
        draw.rectangle((0, 0, width, y0), fill=fill)
    if y1 < height:
        draw.rectangle((0, y1, width, height), fill=fill)
    if x0 > 0 and y1 > y0:
        draw.rectangle((0, y0, x0, y1), fill=fill)
    if x1 < width and y1 > y0:
        draw.rectangle((x1, y0, width, y1), fill=fill)
    draw.rectangle((x0, y0, max(x0, x1 - 1), max(y0, y1 - 1)), outline=outline, width=3)
    return Image.alpha_composite(base, overlay).convert("RGB")


def review_image(image: Image.Image, analysis: PreprocessAnalysis) -> Image.Image:
    corrected = deskew_image(image, analysis.applied_angle_deg)
    return overlay_excluded_regions(corrected, analysis.crop_box)


def processed_image(image: Image.Image, analysis: PreprocessAnalysis) -> Image.Image:
    corrected = deskew_image(image, analysis.applied_angle_deg)
    return corrected.crop(analysis.crop_box)


def preview_output_root(project_root: Path) -> Path:
    path = image_preprocess_output_root(project_root) / "previews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def processed_output_root(project_root: Path) -> Path:
    path = image_preprocess_output_root(project_root) / "processed"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_review_preview(
    page: Path,
    analysis: PreprocessAnalysis,
    destination: Path,
    *,
    max_long_side: int = 1400,
) -> Path:
    with Image.open(page) as opened:
        preview = review_image(opened, analysis)
    scale = min(1.0, max(320, int(max_long_side)) / max(preview.size))
    if scale < 1.0:
        preview = preview.resize(
            (max(1, round(preview.width * scale)), max(1, round(preview.height * scale))),
            Image.Resampling.LANCZOS,
        )
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    preview.save(destination, format="JPEG", quality=88, optimize=True)
    return destination


def save_processed_page(page: Path, analysis: PreprocessAnalysis, destination: Path) -> Path:
    with Image.open(page) as opened:
        result = processed_image(opened, analysis)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    suffix = destination.suffix.casefold()
    if suffix in {".jpg", ".jpeg"}:
        result.save(destination, quality=95, subsampling=0)
    elif suffix in {".tif", ".tiff"}:
        result.save(destination, compression="tiff_lzw")
    else:
        result.save(destination)
    return destination


def result_summary(analysis: PreprocessAnalysis) -> str:
    x0, y0, x1, y1 = analysis.crop_box
    label = "需检查" if analysis.status == "review" else "正常"
    return (
        f"{label}｜纠偏 {analysis.applied_angle_deg:+.2f}°"
        f"（检测 {analysis.correction_angle_deg:+.2f}°）｜"
        f"保留 {analysis.retained_ratio * 100:.1f}%｜"
        f"裁剪 L{x0} T{y0} R{x1} B{y1}"
    )
