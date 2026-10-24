"""Full-resolution VB.NET separator Y search, no implicit core imports.

Call-time callbacks preserve historical brightness scaling and monkeypatching.
"""
from __future__ import annotations
from typing import Any


def find_separator_y(
    rgb_sum: Any,
    candidate_x: int,
    candidate_y: int,
    *,
    column_width: int,
    direction: int,
    row_height: int,
    upward_ratio: float,
    ordinary_right_divisor: float,
    darkness_threshold: int,
    white_threshold_high: int,
    white_threshold_low: int,
    whitespace_adjustment: int,
    top: int,
    x_min: int,
    x_max: int,
    np_module: Any,
    row_brightness_fn: Any,
    brightness_scores_fn: Any,
) -> tuple[int | None, dict[str, int | str]]:
    """Port the two-stage Y search from VB.NET Draw_Auto() at source resolution."""
    np = np_module
    _legacy_row_brightness_1000 = row_brightness_fn
    legacy_row_brightness_scores_1000 = brightness_scores_fn
    height, width = rgb_sum.shape[:2]
    if height <= 0 or width <= 0:
        return None, {"reason": "empty_image"}

    direction = 1 if int(direction) >= 0 else -1
    row_height = max(1, int(row_height))
    upward_ratio = max(0.1, float(upward_ratio))
    upward = max(1, int(round(row_height / upward_ratio)))
    divisor = max(1.0, float(ordinary_right_divisor))
    requested_span = max(1, int(round(float(column_width) / divisor * 0.98)))
    if direction > 0:
        room = min(width - 1, int(x_max)) - int(candidate_x)
    else:
        room = int(candidate_x) - max(0, int(x_min))
    span = max(0, min(requested_span, int(room)))
    if span <= 0:
        return None, {"reason": "empty_horizontal_span"}

    high = max(0, min(1000, int(white_threshold_high)))
    low = max(0, min(1000, int(white_threshold_low)))
    if low > high:
        low, high = high, low
    adjust = max(0, int(whitespace_adjustment))
    dark_limit = max(0, min(765, int(darkness_threshold)))
    xs = int(candidate_x) + direction * np.arange(1, span + 1, dtype=np.int64)

    # VB method 1: nearest upward row with no pixel darker than the fixed
    # threshold, followed by a short run-of-white centering correction.
    for ysu in range(1, upward + 1):
        line_y = int(candidate_y) - ysu
        if line_y < int(top):
            break
        row_values = rgb_sum[line_y, xs]
        if bool(np.any(row_values < dark_limit)):
            continue

        extra_white = 0
        if int(candidate_y) - ysu - int(top) > row_height and adjust > 0:
            for offset in range(1, adjust + 1):
                score = _legacy_row_brightness_1000(
                    rgb_sum, line_y - offset, candidate_x, span, direction=direction
                )
                if score is not None and score >= high:
                    extra_white += 1
                else:
                    break
        separator = int(round(int(candidate_y) - (ysu + extra_white * 0.5)))
        separator = min(int(candidate_y), max(int(top), separator))
        return separator, {
            "reason": "vb_full_white",
            "upward_offset": int(ysu),
            "span": int(span),
            "extra_white_rows": int(extra_white),
        }

    row_scores = legacy_row_brightness_scores_1000(
        rgb_sum, xs, int(top), int(candidate_y), upward, span,
    )
    for threshold in range(high, low - 1, -2):
        for ysu in range(1, upward + 1):
            line_y = int(candidate_y) - ysu
            if line_y < int(top):
                break
            score = row_scores.get(line_y)
            if score is None or score <= threshold:
                continue

            separator = line_y
            if adjust > 0 and ysu < adjust:
                for ygiu in range(ysu, upward + 1):
                    probe_y = int(candidate_y) - ygiu
                    if probe_y < int(top):
                        break
                    probe = row_scores.get(probe_y)
                    if probe is None:
                        break
                    if probe < low or probe + 50 < threshold:
                        separator = int(candidate_y) - ygiu + adjust
                        break
            separator = min(int(candidate_y), max(int(top), int(separator)))
            return separator, {
                "reason": "vb_brightness_fallback",
                "upward_offset": int(ysu),
                "span": int(span),
                "threshold": int(threshold),
            }

    return None, {"reason": "no_vb_separator", "span": int(span)}
