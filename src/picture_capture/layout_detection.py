from __future__ import annotations

import os
import gc
import statistics
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .models import AppSettings
from .image_utils import normalize_page_rgb
from .layout_transform import LayoutTransform
from .processing import parameter_scale


@dataclass(slots=True)
class LayoutEstimate:
    columns: int
    start_y: int
    column_width: int
    gutter: int
    manual_x: int
    bottom_y: int
    character_height: int
    row_padding: int
    source_boxes: int
    method: str = "paddle"
    canonical_transform: str = "identity"
    separator_x: int | None = None
    confidence: float = 0.0


@dataclass(slots=True)
class LayoutConsistencyEstimate:
    header_rule_y: int | None
    body_left_x: int | None
    is_blank: bool = False


@dataclass(frozen=True, slots=True)
class VerticalRuleEstimate:
    rule_start: int
    rule_end: int
    gutter_start: int
    gutter_end: int
    confidence: float

    @property
    def center(self) -> int:
        return round((self.rule_start + self.rule_end) / 2)


def aggregate_layout_estimates(
    estimates: Iterable[LayoutEstimate], *, columns_policy: str = "detect", fixed_columns: int | None = None
) -> tuple[dict[str, int], str]:
    """Robustly combine page estimates and report column consistency.

    Columns use a mode (or the Profile's fixed prior); continuous geometry uses
    a median after conservative MAD outlier rejection.
    """
    rows = list(estimates)
    if not rows:
        raise ValueError("At least one layout estimate is required")
    observed = [max(1, int(row.columns)) for row in rows]
    counts = {value: observed.count(value) for value in set(observed)}
    mode_columns = min(counts, key=lambda value: (-counts[value], value))
    columns = max(1, int(fixed_columns or mode_columns)) if columns_policy == "fixed" else mode_columns

    def robust_median(name: str) -> int:
        values = [float(getattr(row, name)) for row in rows]
        center = statistics.median(values)
        deviations = [abs(value - center) for value in values]
        mad = statistics.median(deviations)
        kept = values if mad == 0 else [value for value in values if abs(value - center) <= 3.5 * mad]
        return round(statistics.median(kept or values))

    result = {"columns": columns}
    for field in ("start_y", "bottom_y", "manual_x", "column_width", "gutter", "character_height", "row_padding"):
        result[field] = robust_median(field)
    # Leave a small safety margin above the first detected body line instead of
    # placing the header boundary directly against text.  This value is already
    # in the user-facing parameter coordinate system.
    result["start_y"] = max(0, result["start_y"] - 5)
    result["row_padding"] = max(1, result["row_padding"])
    return result, f"{columns}栏: {counts.get(columns, 0)}/{len(rows)} pages"


_TEXT_DETECTION_CACHE: dict[str, Any] = {}


def clear_text_detection_cache() -> None:
    """Release cached layout-only detectors before full OCR is constructed."""
    if _TEXT_DETECTION_CACHE:
        _TEXT_DETECTION_CACHE.clear()
        gc.collect()


def _result_payload(result: Any) -> dict[str, Any]:
    payload = getattr(result, "json", result)
    if callable(payload):
        payload = payload()
    if not isinstance(payload, dict):
        raise RuntimeError("PaddleOCR TextDetection 返回了无法解析的结果格式")
    nested = payload.get("res")
    return nested if isinstance(nested, dict) else payload


def _get_text_detector(settings: AppSettings) -> Any:
    """Create a detection-only PaddleOCR model with CPU oneDNN/PIR disabled.

    PaddlePaddle 3.3.x + recent PaddleOCR builds can enter a PIR/oneDNN CPU
    execution path that raises ConvertPirAttribute2RuntimeAttribute for text
    detection models.  Layout detection values compatibility over peak speed,
    so explicitly disable that acceleration path here.
    """
    key = f"{settings.paddle_device or 'cpu'}|nomkldnn"
    if key in _TEXT_DETECTION_CACHE:
        return _TEXT_DETECTION_CACHE[key]

    # Must be set before importing/constructing PaddleOCR/PaddleX components.
    # This is intentionally an assignment (not setdefault): some PaddleX builds
    # may have set it to 1 earlier in the process.
    os.environ["FLAGS_enable_pir_api"] = "0"
    from .windows_gpu_runtime import configure_windows_nvidia_dlls
    configure_windows_nvidia_dlls()
    try:
        from paddleocr import TextDetection
    except ImportError as exc:
        raise RuntimeError(
            "尚未安装 PaddleOCR。Windows 请运行 install_ocr_windows.bat；CPU 用户也可执行：uv sync --extra ocr-cpu"
        ) from exc

    kwargs: dict[str, Any] = {"enable_mkldnn": False}
    if settings.paddle_device:
        kwargs["device"] = settings.paddle_device

    # Newer PaddleOCR 3.x exposes enable_mkldnn directly.  Keep compatibility
    # with older 3.x signatures by progressively dropping unsupported kwargs.
    attempts = [
        kwargs,
        {k: v for k, v in kwargs.items() if k != "device"},
        {"device": settings.paddle_device} if settings.paddle_device else {},
        {},
    ]
    seen: set[tuple[tuple[str, str], ...]] = set()
    last_exc: Exception | None = None
    for attempt in attempts:
        marker = tuple(sorted((str(k), repr(v)) for k, v in attempt.items()))
        if marker in seen:
            continue
        seen.add(marker)
        try:
            detector = TextDetection(**attempt)
            # Layout detection only needs the active device configuration.
            # Keeping stale detector instances for every past device can pin
            # substantial Paddle/PaddleX memory for the whole GUI session.
            _TEXT_DETECTION_CACHE.clear()
            _TEXT_DETECTION_CACHE[key] = detector
            return detector
        except TypeError as exc:
            last_exc = exc
            continue
        except Exception as exc:
            last_exc = exc
            break
    raise RuntimeError(f"PaddleOCR 文本检测模型初始化失败：{last_exc}") from last_exc


def _boxes_from_detection(result: Any, width: int, height: int) -> list[tuple[int, int, int, int]]:
    payload = _result_payload(result)
    raw_polys = payload.get("dt_polys")
    if raw_polys is None:
        raw_polys = payload.get("polys")
    if raw_polys is None:
        return []
    boxes: list[tuple[int, int, int, int]] = []
    for raw in list(raw_polys):
        arr = np.asarray(raw, dtype=float)
        if arr.ndim != 2 or arr.shape[0] < 3 or arr.shape[1] < 2:
            continue
        x0 = max(0, min(width - 1, int(round(float(arr[:, 0].min())))))
        x1 = max(1, min(width, int(round(float(arr[:, 0].max())))))
        y0 = max(0, min(height - 1, int(round(float(arr[:, 1].min())))))
        y1 = max(1, min(height, int(round(float(arr[:, 1].max())))))
        if x1 - x0 >= 3 and y1 - y0 >= 3:
            boxes.append((x0, y0, x1, y1))
    return boxes


def _split_left_edge_groups(
    boxes: list[tuple[int, int, int, int]], width: int
) -> list[list[tuple[int, int, int, int]]]:
    if not boxes:
        return []
    ordered = sorted(boxes, key=lambda box: box[0])
    split_gap = max(36, int(round(width * 0.14)))
    groups: list[list[tuple[int, int, int, int]]] = [[ordered[0]]]
    for box in ordered[1:]:
        if box[0] - groups[-1][-1][0] >= split_gap:
            groups.append([box])
        else:
            groups[-1].append(box)

    minimum = max(4, int(round(len(boxes) * 0.055)))
    useful = [group for group in groups if len(group) >= minimum]
    if not useful:
        useful = [max(groups, key=len)]
    useful.sort(key=lambda group: float(np.percentile([b[0] for b in group], 10)))
    return useful[:6]


def _longest_low_density_run(
    density: np.ndarray, start: int, end: int
) -> tuple[int, int] | None:
    if end <= start + 3:
        return None
    region = density[start:end]
    positive = region[region > 0]
    if positive.size:
        threshold = max(float(np.percentile(positive, 12)) * 0.35, float(region.max()) * 0.018)
    else:
        threshold = 0.0
    mask = region <= threshold
    best: tuple[int, int] | None = None
    run_start: int | None = None
    for i, flag in enumerate(mask):
        if flag and run_start is None:
            run_start = i
        if (not flag or i == len(mask) - 1) and run_start is not None:
            run_end = i if not flag else i + 1
            if best is None or run_end - run_start > best[1] - best[0]:
                best = (start + run_start, start + run_end)
            run_start = None
    return best


def _persistent_vertical_whitespace(ink: np.ndarray) -> np.ndarray:
    """Mark columns that stay nearly ink-free throughout most body blocks.

    A short dictionary definition can make a large *aggregate* empty area, but
    it does not make the same X coordinate empty in most vertical body blocks.
    This persistence test is therefore much less likely to mistake ragged line
    endings for an inter-column gutter.
    """
    if ink.ndim != 2 or ink.shape[0] < 2:
        return np.zeros(ink.shape[-1] if ink.ndim else 0, dtype=bool)
    overall = ink.mean(axis=0)
    positive = overall[overall > 0]
    overall_limit = max(0.0015, float(np.percentile(positive, 12)) * 0.28) if positive.size else 0.0015
    blocks = [block for block in np.array_split(ink, min(16, max(4, ink.shape[0] // 80)), axis=0) if block.size]
    block_density = np.vstack([block.mean(axis=0) for block in blocks])
    block_limit = max(0.003, overall_limit * 1.8)
    persistent = (overall <= overall_limit) & ((block_density <= block_limit).mean(axis=0) >= 0.75)

    # Bridge scanner specks or a one-pixel vertical blemish inside an otherwise
    # continuous gutter, without expanding genuinely nonblank regions.
    bridge = max(1, round(ink.shape[1] * 0.0015))
    for start, end in _runs(~persistent):
        if start > 0 and end < len(persistent) and end - start <= bridge:
            persistent[start:end] = True
    return persistent


def _gutter_before_next_start(
    ink: np.ndarray, left: int, right: int, body_top: int, body_bottom: int
) -> tuple[int, int] | None:
    """Find the rightmost persistent whitespace band before the next column."""
    pitch = right - left
    if pitch <= 10:
        return None
    top = max(0, min(ink.shape[0] - 1, int(body_top)))
    bottom = max(top + 1, min(ink.shape[0], int(body_bottom)))
    stable_blank = _persistent_vertical_whitespace(ink[top:bottom, :])
    search_left = max(left + round(pitch * 0.38), 0)
    search_right = min(right, len(stable_blank))
    minimum = max(5, round(ink.shape[1] * 0.005))
    candidates = [
        (search_left + start, search_left + end)
        for start, end in _runs(stable_blank[search_left:search_right])
        if end - start >= minimum
    ]
    return max(candidates, key=lambda run: (run[1], run[0])) if candidates else None


def _detect_persistent_vertical_rule(
    ink: np.ndarray, left: int, right: int, body_top: int, body_bottom: int, mode: str = "auto"
) -> VerticalRuleEstimate | None:
    """Detect a narrow persistent divider and include blank space on both sides."""
    if mode == "absent" or right - left < 20 or ink.ndim != 2:
        return None
    top = max(0, min(ink.shape[0] - 1, int(body_top)))
    bottom = max(top + 1, min(ink.shape[0], int(body_bottom)))
    body = ink[top:bottom]
    pitch = right - left
    search_left = max(0, left + round(pitch * 0.45))
    search_right = min(ink.shape[1], right - max(2, round(pitch * 0.02)))
    if search_right <= search_left:
        return None
    blocks = [block for block in np.array_split(body, min(20, max(5, body.shape[0] // 60)), axis=0) if block.size]
    density = body.mean(axis=0)
    persistence = np.vstack([block.mean(axis=0) >= 0.18 for block in blocks]).mean(axis=0)
    threshold = 0.45 if mode == "present" else 0.68
    candidates = (persistence >= threshold) & (density >= (0.22 if mode == "present" else 0.34))
    max_width = max(3, min(round(pitch * 0.035), round(ink.shape[1] * 0.012)))
    runs = [
        (search_left + a, search_left + b)
        for a, b in _runs(candidates[search_left:search_right])
        if 1 <= b - a <= max_width
    ]
    if not runs:
        return None
    rule_start, rule_end = max(
        runs, key=lambda run: float(persistence[run[0]:run[1]].mean()) - (run[1] - run[0]) * 0.002
    )
    stable_blank = _persistent_vertical_whitespace(body)
    # The whitespace helper deliberately bridges tiny interruptions so broken
    # scans still form a useful gutter.  A real divider is precisely such a
    # tiny interruption, however, so split the mask back at the detected rule
    # before looking for its two adjacent blank regions.
    stable_blank[rule_start:rule_end] = False
    blank_runs = _runs(stable_blank)
    left_blanks = [run for run in blank_runs if run[1] <= rule_start and rule_start - run[1] <= max_width + 3]
    right_blanks = [run for run in blank_runs if run[0] >= rule_end and run[0] - rule_end <= max_width + 3]
    minimum_blank = max(2, round(pitch * 0.008))
    if mode == "auto" and (
        not left_blanks
        or not right_blanks
        or left_blanks[-1][1] - left_blanks[-1][0] < minimum_blank
        or right_blanks[0][1] - right_blanks[0][0] < minimum_blank
    ):
        return None
    gutter_start = max(left_blanks, key=lambda run: run[1])[0] if left_blanks else rule_start
    gutter_end = min(right_blanks, key=lambda run: run[0])[1] if right_blanks else rule_end
    confidence = float(persistence[rule_start:rule_end].mean())
    return VerticalRuleEstimate(rule_start, rule_end, gutter_start, gutter_end, confidence)


def _estimate_start_y(boxes: list[tuple[int, int, int, int]], height: int) -> int:
    if not boxes:
        return 0
    heights = [box[3] - box[1] for box in boxes]
    median_h = max(4.0, float(np.median(heights)))
    intervals = sorted((box[1], box[3]) for box in boxes)
    merged: list[list[int]] = []
    merge_gap = max(2, int(round(median_h * 0.25)))
    for y0, y1 in intervals:
        if not merged or y0 > merged[-1][1] + merge_gap:
            merged.append([y0, y1])
        else:
            merged[-1][1] = max(merged[-1][1], y1)

    top_limit = int(round(height * 0.36))
    candidates: list[tuple[int, int]] = []
    for prev, nxt in zip(merged, merged[1:]):
        gap = nxt[0] - prev[1]
        if nxt[0] <= top_limit and gap >= median_h * 1.45:
            candidates.append((gap, nxt[0]))
    if candidates:
        _gap, y = max(candidates)
        return int(y)
    return int(np.percentile([box[1] for box in boxes], 2))


def infer_layout_from_boxes(
    boxes: Iterable[tuple[int, int, int, int]],
    image_size: tuple[int, int],
    display_scale: float = 1.0,
    ink_mask: np.ndarray | None = None,
    columns_policy: str = "detect",
    fixed_columns: int | None = None,
    column_separator_mode: str = "auto",
) -> LayoutEstimate:
    width, height = image_size
    raw = [
        tuple(map(int, box)) for box in boxes
        if box[2] > box[0] and box[3] > box[1]
    ]
    if len(raw) < 4:
        raise RuntimeError("整页文本检测框过少，无法可靠估计版面参数。")

    median_h = float(np.median([box[3] - box[1] for box in raw]))
    filtered = [
        box for box in raw
        if box[3] - box[1] >= max(3.0, median_h * 0.40)
        and box[2] - box[0] <= width * 0.92
    ] or raw

    groups = _split_left_edge_groups(filtered, width)
    starts = [int(round(float(np.percentile([box[0] for box in group], 6)))) for group in groups]
    starts = sorted(set(starts))
    if not starts:
        starts = [int(np.percentile([box[0] for box in filtered], 4))]
    if columns_policy == "fixed" and fixed_columns:
        count = max(1, min(12, int(fixed_columns)))
        page_left = int(np.percentile([box[0] for box in filtered], 4))
        observed_right = int(np.percentile([box[2] for box in filtered], 98))
        # Sparse pages may contain text in only the first column.  Under a
        # fixed-column prior, use the symmetric page extent rather than
        # compressing every configured column into that one occupied region.
        page_right = max(observed_right, width - page_left)
        pitch = max(10.0, (page_right - page_left) / count)
        constrained: list[int] = []
        for index in range(count):
            expected = page_left + index * pitch
            nearby = [box[0] for box in filtered if abs(box[0] - expected) <= pitch * 0.28]
            constrained.append(int(np.percentile(nearby, 8)) if nearby else round(expected))
        starts = constrained

    density = np.zeros(max(1, width), dtype=float)
    for x0, y0, x1, y1 in filtered:
        density[max(0, x0):min(width, x1)] += max(1, y1 - y0)

    gap_widths: list[int] = []
    col_widths: list[int] = []
    body_top = _estimate_start_y(filtered, height)
    body_bottom = int(np.percentile([box[3] for box in filtered], 99))
    separators: list[int] = []
    for left, right in zip(starts, starts[1:]):
        pitch = right - left
        divider = (
            _detect_persistent_vertical_rule(
                ink_mask,
                left,
                right,
                body_top,
                body_bottom,
                column_separator_mode,
            )
            if ink_mask is not None
            else None
        )
        if divider is not None:
            run = (divider.gutter_start, divider.gutter_end)
            separators.append(divider.center)
        else:
            run = None
        run = run or (
            _gutter_before_next_start(ink_mask, left, right, body_top, body_bottom)
            if ink_mask is not None else None
        )
        if run is None:
            search_left = left + max(6, int(round(pitch * 0.42)))
            search_right = right - max(4, int(round(pitch * 0.035)))
            run = _longest_low_density_run(density, search_left, search_right)
        if run and run[1] - run[0] >= max(6, int(round(width * 0.006))):
            gap_start, gap_end = run
            gap_widths.append(gap_end - gap_start)
            col_widths.append(max(10, gap_start - left))
        else:
            fallback_gutter = max(8, int(round(pitch * 0.055)))
            gap_widths.append(fallback_gutter)
            col_widths.append(max(10, pitch - fallback_gutter))

    if len(starts) == 1:
        right_edges = [box[2] for box in filtered if box[0] >= starts[0] - width * 0.04]
        right = int(np.percentile(right_edges, 97)) if right_edges else width - starts[0]
        col_widths = [max(10, right - starts[0])]
        gutter_source = 0
    else:
        col_widths.append(int(round(float(np.median(col_widths)))))
        gutter_source = int(round(float(np.median(gap_widths)))) if gap_widths else 0

    start_y_source = body_top
    bottom_y_source = body_bottom
    character_height_source = max(1, round(float(np.median([box[3] - box[1] for box in filtered]))))
    ordered_tops = sorted({box[1] for box in filtered})
    top_steps = [b - a for a, b in zip(ordered_tops, ordered_tops[1:]) if b - a > character_height_source * 0.5]
    row_padding_source = max(1, round((float(np.median(top_steps)) - character_height_source) / 2)) if top_steps else 1
    scale = max(0.01, float(display_scale))
    return LayoutEstimate(
        columns=len(starts),
        start_y=max(0, round(start_y_source * scale)),
        column_width=max(10, round(float(np.median(col_widths)) * scale)),
        gutter=max(0, round(gutter_source * scale)),
        manual_x=max(0, round(starts[0] * scale)),
        bottom_y=max(1, round(bottom_y_source * scale)),
        character_height=max(1, round(character_height_source * scale)),
        row_padding=max(1, round(row_padding_source * scale)),
        source_boxes=len(filtered),
        method="paddle",
        separator_x=(round(float(np.median(separators)) * scale) if separators else None),
    )


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    start: int | None = None
    for i, flag in enumerate(mask.tolist()):
        if flag and start is None:
            start = i
        if start is not None and (not flag or i == len(mask) - 1):
            end = i if not flag else i + 1
            result.append((start, end))
            start = None
    return result


def _smooth_1d(values: np.ndarray, window: int) -> np.ndarray:
    window = max(1, int(window))
    if window <= 1:
        return values.astype(float, copy=False)
    kernel = np.ones(window, dtype=float) / window
    return np.convolve(values.astype(float), kernel, mode="same")


def _otsu_threshold(gray: np.ndarray) -> int:
    hist = np.bincount(gray.ravel(), minlength=256).astype(float)
    total = hist.sum()
    if total <= 0:
        return 200
    cumulative = np.cumsum(hist)
    means = np.cumsum(hist * np.arange(256))
    global_mean = means[-1]
    denom = cumulative * (total - cumulative)
    valid = denom > 0
    score = np.zeros(256, dtype=float)
    score[valid] = (global_mean * cumulative[valid] - means[valid] * total) ** 2 / denom[valid]
    # Do not let very bright paper noise become foreground on faint scans.
    return int(min(235, max(80, int(np.argmax(score)))))


def _analysis_ink_mask(gray: np.ndarray, settings: AppSettings) -> np.ndarray:
    """Build the layout-analysis foreground mask from the configured threshold mode."""
    mode = str(getattr(settings, "analysis_threshold_mode", "auto") or "auto").strip().lower()
    if mode == "fixed":
        # Legacy darkness_threshold is an RGB-channel sum; grayscale is per-channel.
        threshold = int(round(float(getattr(settings, "darkness_threshold", 600)) / 3.0))
        threshold = min(255, max(0, threshold))
        return gray < threshold
    if mode == "adaptive":
        # Local background estimate for uneven/yellowed scans. Keep this deterministic
        # and dependency-free; a modest box blur is enough for layout projections.
        radius = max(3, round(min(gray.shape[:2]) * 0.008))
        local = np.asarray(
            Image.fromarray(gray, mode="L").filter(ImageFilter.BoxBlur(radius=radius)),
            dtype=np.int16,
        )
        return gray.astype(np.int16) < (local - 10)
    # "auto" and explicit "otsu" intentionally share the conservative Otsu path.
    return gray < _otsu_threshold(gray)


def _projection_layout_estimate(source: Image.Image, settings: AppSettings) -> LayoutEstimate:
    """OCR-free fallback based on dark-pixel projections.

    This is only used when PaddleOCR's detector cannot run in the installed
    Paddle/PaddleX stack.  It has no user-facing projection parameters and does
    not revive the removed projection-based headword drawing mode.
    """
    original_w, original_h = source.size
    max_dim = max(original_w, original_h)
    resize_scale = min(1.0, 1800.0 / max(1, max_dim))
    if resize_scale < 1.0:
        work = source.resize(
            (max(1, round(original_w * resize_scale)), max(1, round(original_h * resize_scale))),
            Image.Resampling.BILINEAR,
        )
    else:
        work = source
    gray = np.asarray(ImageOps.grayscale(work), dtype=np.uint8)
    h, w = gray.shape
    ink = _analysis_ink_mask(gray, settings)

    # Ignore a narrow outer rim where scanner shadows/page borders live.
    mx = max(1, round(w * 0.015)); my = max(1, round(h * 0.01))
    ink[:my, :] = False; ink[-my:, :] = False
    ink[:, :mx] = False; ink[:, -mx:] = False

    row_density = _smooth_1d(ink.mean(axis=1), max(3, round(h * 0.0025)))
    active_floor = max(0.002, float(np.percentile(row_density[row_density > 0], 25)) * 0.35) if np.any(row_density > 0) else 0.002
    blank_rows = row_density <= active_floor
    early_limit = max(1, round(h * 0.38))
    header_gaps = [
        (a, b) for a, b in _runs(blank_rows[:early_limit])
        if b - a >= max(6, round(h * 0.006)) and a > round(h * 0.015)
    ]
    if header_gaps:
        # Prefer the largest early whitespace band.  Its lower edge usually
        # marks the start of dictionary body text after a running header/title.
        start_y_small = max(header_gaps, key=lambda run: run[1] - run[0])[1]
    else:
        active_idx = np.flatnonzero(~blank_rows)
        start_y_small = int(active_idx[0]) if active_idx.size else 0

    body_top = min(max(0, start_y_small), max(0, h - 1))
    body_bottom = max(body_top + 1, round(h * 0.97))
    body = ink[body_top:body_bottom, :]
    x_density = _smooth_1d(body.mean(axis=0), max(5, round(w * 0.006)))
    positive = x_density[x_density > 0]
    if positive.size == 0:
        raise RuntimeError("图像回退检测未发现可用正文像素。")
    blank_threshold = max(0.001, float(np.percentile(positive, 18)) * 0.38)
    blank_cols = _persistent_vertical_whitespace(body)

    min_gap = max(6, round(w * 0.008))
    gap_candidates = [
        (a, b) for a, b in _runs(blank_cols)
        if b - a >= min_gap
        and a >= round(w * 0.05)
        and b <= round(w * 0.95)
    ]

    # Keep only gaps that leave plausible dictionary columns on both sides.
    # Greedy by width makes real inter-column gutters win over accidental
    # whitespace created by short definitions.
    chosen: list[tuple[int, int]] = []
    for gap in sorted(gap_candidates, key=lambda g: (g[1] - g[0]), reverse=True):
        center = (gap[0] + gap[1]) / 2
        if any(abs(center - (g[0] + g[1]) / 2) < w * 0.12 for g in chosen):
            continue
        test = sorted(chosen + [gap])
        edges = [round(w * 0.03)] + [int((a + b) / 2) for a, b in test] + [round(w * 0.97)]
        widths = [b - a for a, b in zip(edges, edges[1:])]
        if widths and min(widths) >= w * 0.13:
            chosen.append(gap)
        if len(chosen) >= 5:
            break
    chosen.sort()

    text_mask = x_density > blank_threshold
    text_positions = np.flatnonzero(text_mask)
    if not text_positions.size:
        raise RuntimeError("图像回退检测无法确定正文水平范围。")
    page_left = int(text_positions[0]); page_right = int(text_positions[-1] + 1)

    starts: list[int] = []
    widths: list[int] = []
    gutters: list[int] = []
    region_left = page_left
    for gap_start, gap_end in chosen:
        region = np.flatnonzero(text_mask[region_left:gap_start])
        if region.size:
            start = region_left + int(region[0])
            starts.append(start)
            widths.append(max(10, gap_start - start))
            gutters.append(gap_end - gap_start)
        region_left = gap_end
    region = np.flatnonzero(text_mask[region_left:page_right])
    if region.size:
        start = region_left + int(region[0])
        starts.append(start)
        widths.append(max(10, page_right - start))

    if not starts:
        starts = [page_left]
        widths = [max(10, page_right - page_left)]
        gutters = []
    if len(starts) > 1:
        # Last column may have shorter lines; use preceding widths as the more
        # stable estimate of the designed column width.
        stable = widths[:-1] if widths[:-1] else widths
        widths[-1] = int(round(float(np.median(stable))))

    separator_centers: list[int] = []
    if settings.layout_columns_policy == "fixed":
        count = max(1, min(12, int(settings.columns)))
        span = max(10.0, (page_right - page_left) / count)
        starts = []
        for index in range(count):
            zone_left = round(page_left + index * span)
            zone_right = round(page_left + (index + 0.35) * span)
            search_left = zone_left
            if index and settings.layout_column_separator_mode != "absent":
                search_left += max(3, round(span * 0.02))
            # A central rule may be the first dark feature in the next slot.
            # Exclude unusually persistent columns when finding the leading
            # edge; ordinary glyph columns vary down the page, while a divider
            # remains dark through most body rows.
            leading_mask = text_mask & (x_density < 0.72)
            positions = np.flatnonzero(leading_mask[search_left:zone_right])
            if not positions.size:
                minimum_text_run = max(4, round(span * 0.015))
                text_runs = [
                    (a, b)
                    for a, b in _runs(text_mask[search_left:zone_right])
                    if b - a >= minimum_text_run
                ]
                if text_runs:
                    positions = np.arange(text_runs[0][0], text_runs[0][1])
            starts.append(search_left + int(positions[0]) if positions.size else zone_left)
        widths = []
        gutters = []
        for left, right in zip(starts, starts[1:]):
            divider = _detect_persistent_vertical_rule(
                ink,
                left,
                right,
                body_top,
                body_bottom,
                settings.layout_column_separator_mode,
            )
            run = (
                (divider.gutter_start, divider.gutter_end)
                if divider
                else _gutter_before_next_start(ink, left, right, body_top, body_bottom)
            )
            if divider:
                separator_centers.append(divider.center)
            if run:
                widths.append(max(10, run[0] - left))
                gutters.append(run[1] - run[0])
            else:
                fallback = max(8, round((right - left) * 0.055))
                widths.append(max(10, right - left - fallback))
                gutters.append(fallback)
        if count == 1:
            widths = [max(10, page_right - starts[0])]
            gutters = []
        else:
            widths.append(round(float(np.median(widths))))

    back = 1.0 / resize_scale
    display = parameter_scale(source, settings)
    factor = back * display
    return LayoutEstimate(
        columns=max(1, min(6, len(starts))),
        start_y=max(0, round(start_y_small * factor)),
        column_width=max(10, round(float(np.median(widths)) * factor)),
        gutter=max(0, round((float(np.median(gutters)) if gutters else 0.0) * factor)),
        manual_x=max(0, round(starts[0] * factor)),
        bottom_y=max(1, round(body_bottom * factor)),
        character_height=max(1, round(max(1, h * 0.008) * factor)),
        row_padding=1,
        source_boxes=max(1, len(starts) + len(chosen)),
        method="projection_fallback",
        separator_x=(round(float(np.median(separator_centers)) * factor) if separator_centers else None),
    )


def detect_layout_parameters(image: Image.Image, settings: AppSettings) -> LayoutEstimate:
    """Detect dictionary page geometry without OCR text recognition.

    Primary path: PaddleOCR TextDetection with CPU oneDNN/PIR disabled.
    Compatibility path: OCR-free image-density layout estimation when the
    installed Paddle/PaddleX stack still cannot execute detection.
    """
    source = normalize_page_rgb(image)
    transform = LayoutTransform(settings.layout_transform)  # type: ignore[arg-type]
    analysis = transform.canonical_image_for_analysis(source)
    paddle_error: Exception | None = None
    try:
        detector = _get_text_detector(settings)
        # Reassert immediately before predict because PaddleX can modify flags
        # while constructing other pipelines in the same application process.
        os.environ["FLAGS_enable_pir_api"] = "0"
        try:
            results = list(detector.predict(np.asarray(analysis), batch_size=1, limit_side_len=2400))
        except TypeError:
            results = list(detector.predict(np.asarray(analysis)))
        if results:
            boxes = _boxes_from_detection(results[0], analysis.width, analysis.height)
            if boxes:
                source_gray = np.asarray(ImageOps.grayscale(analysis), dtype=np.uint8)
                estimate = infer_layout_from_boxes(
                    boxes,
                    analysis.size,
                    display_scale=parameter_scale(analysis, settings),
                    ink_mask=_analysis_ink_mask(source_gray, settings),
                    columns_policy=settings.layout_columns_policy,
                    fixed_columns=settings.columns,
                    column_separator_mode=settings.layout_column_separator_mode,
                )
                estimate.canonical_transform = transform.kind
                estimate.confidence = min(1.0, estimate.source_boxes / 40.0)
                return estimate
            paddle_error = RuntimeError("PaddleOCR 整页版面检测没有返回文本框。")
        else:
            paddle_error = RuntimeError("PaddleOCR 整页版面检测没有返回结果。")
    except Exception as exc:
        paddle_error = exc

    try:
        estimate = _projection_layout_estimate(analysis, settings)
        estimate.canonical_transform = transform.kind
        estimate.confidence = min(1.0, estimate.source_boxes / 6.0)
        return estimate
    except Exception as fallback_exc:
        raise RuntimeError(
            f"PaddleOCR 整页版面检测失败：{paddle_error}\n"
            f"兼容回退检测也失败：{fallback_exc}"
        ) from fallback_exc


def detect_layout_consistency(image: Image.Image, settings: AppSettings) -> LayoutConsistencyEstimate:
    """Quickly measure header-rule Y and first body-text X using projections.

    This deliberately avoids OCR/VLM inference: downscaled grayscale projections
    are deterministic and substantially cheaper for projects containing thousands
    of pages.
    """
    source = LayoutTransform(settings.layout_transform).canonical_image_for_analysis(
        normalize_page_rgb(image)
    )
    scale = min(1.0, 1600.0 / max(source.size))
    work = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.BILINEAR,
    ) if scale < 1.0 else source
    gray = np.asarray(ImageOps.grayscale(work), dtype=np.uint8)
    ink = _analysis_ink_mask(gray, settings)
    active_rows = int(np.count_nonzero(ink.mean(axis=1) > 0.002))
    active_columns = int(np.count_nonzero(ink.mean(axis=0) > 0.002))
    is_blank = float(ink.mean()) < 0.0008 or active_rows < 6 or active_columns < 12
    if is_blank:
        return LayoutConsistencyEstimate(None, None, is_blank=True)
    parameter_to_source = 1.0 / max(0.01, parameter_scale(source, settings))
    header_limit = min(ink.shape[0], max(1, round(settings.start_y * parameter_to_source * scale)))
    header_density = ink[:header_limit].mean(axis=1)
    header_rule_y: int | None = None
    if header_density.size and float(header_density.max()) >= 0.12:
        header_rule_y = round(int(np.argmax(header_density)) / scale * parameter_scale(source, settings))

    body = ink[header_limit:, :]
    body_left_x: int | None = None
    if body.size:
        column_density = body.mean(axis=0)
        threshold = max(0.002, float(np.percentile(column_density[column_density > 0], 20)) * 0.35) if np.any(column_density > 0) else 0.002
        active = np.flatnonzero(column_density > threshold)
        if active.size:
            body_left_x = round(int(active[0]) / scale * parameter_scale(source, settings))
    return LayoutConsistencyEstimate(header_rule_y=header_rule_y, body_left_x=body_left_x, is_blank=False)
