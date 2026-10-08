from __future__ import annotations

import numpy as np

from picture_capture.processing_core import (
    _legacy_find_separator_y,
    _legacy_row_brightness_1000,
)


def _historical_find_separator_y(
    rgb_sum: np.ndarray,
    candidate_x: int,
    candidate_y: int,
    **kwargs,
):
    height, width = rgb_sum.shape[:2]
    if height <= 0 or width <= 0:
        return None, {"reason": "empty_image"}

    direction = 1 if int(kwargs["direction"]) >= 0 else -1
    row_height = max(1, int(kwargs["row_height"]))
    upward_ratio = max(0.1, float(kwargs["upward_ratio"]))
    upward = max(1, int(round(row_height / upward_ratio)))
    divisor = max(1.0, float(kwargs["ordinary_right_divisor"]))
    requested_span = max(
        1, int(round(float(kwargs["column_width"]) / divisor * 0.98))
    )
    if direction > 0:
        room = min(width - 1, int(kwargs["x_max"])) - int(candidate_x)
    else:
        room = int(candidate_x) - max(0, int(kwargs["x_min"]))
    span = max(0, min(requested_span, int(room)))
    if span <= 0:
        return None, {"reason": "empty_horizontal_span"}

    high = max(0, min(1000, int(kwargs["white_threshold_high"])))
    low = max(0, min(1000, int(kwargs["white_threshold_low"])))
    if low > high:
        low, high = high, low
    adjust = max(0, int(kwargs["whitespace_adjustment"]))
    dark_limit = max(0, min(765, int(kwargs["darkness_threshold"])))
    top = int(kwargs["top"])
    xs = int(candidate_x) + direction * np.arange(1, span + 1, dtype=np.int64)

    for ysu in range(1, upward + 1):
        line_y = int(candidate_y) - ysu
        if line_y < top:
            break
        if bool(np.any(rgb_sum[line_y, xs] < dark_limit)):
            continue
        extra_white = 0
        if int(candidate_y) - ysu - top > row_height and adjust > 0:
            for offset in range(1, adjust + 1):
                score = _legacy_row_brightness_1000(
                    rgb_sum, line_y - offset, candidate_x, span, direction=direction
                )
                if score is not None and score >= high:
                    extra_white += 1
                else:
                    break
        separator = int(round(int(candidate_y) - (ysu + extra_white * 0.5)))
        separator = min(int(candidate_y), max(top, separator))
        return separator, {
            "reason": "vb_full_white",
            "upward_offset": int(ysu),
            "span": int(span),
            "extra_white_rows": int(extra_white),
        }

    for threshold in range(high, low - 1, -2):
        for ysu in range(1, upward + 1):
            line_y = int(candidate_y) - ysu
            if line_y < top:
                break
            score = _legacy_row_brightness_1000(
                rgb_sum, line_y, candidate_x, span, direction=direction
            )
            if score is None or score <= threshold:
                continue
            separator = line_y
            if adjust > 0 and ysu < adjust:
                for ygiu in range(ysu, upward + 1):
                    probe_y = int(candidate_y) - ygiu
                    if probe_y < top:
                        break
                    probe = _legacy_row_brightness_1000(
                        rgb_sum, probe_y, candidate_x, span, direction=direction
                    )
                    if probe is None:
                        break
                    if probe < low or probe + 50 < threshold:
                        separator = int(candidate_y) - ygiu + adjust
                        break
            separator = min(int(candidate_y), max(top, int(separator)))
            return separator, {
                "reason": "vb_brightness_fallback",
                "upward_offset": int(ysu),
                "span": int(span),
                "threshold": int(threshold),
            }
    return None, {"reason": "no_vb_separator", "span": int(span)}


def test_phase8j_cached_fallback_matches_historical_separator_search() -> None:
    rng = np.random.default_rng(20261008)
    for direction, candidate_x in ((1, 20), (-1, 139)):
        for _ in range(30):
            rgb_sum = rng.integers(0, 766, size=(100, 160), dtype=np.uint16)
            kwargs = dict(
                column_width=100,
                direction=direction,
                row_height=20,
                upward_ratio=1.5,
                ordinary_right_divisor=1.0,
                darkness_threshold=300,
                white_threshold_high=999,
                white_threshold_low=700,
                whitespace_adjustment=2,
                top=10,
                x_min=0,
                x_max=159,
            )
            expected = _historical_find_separator_y(
                rgb_sum, candidate_x, 60, **kwargs
            )
            actual = _legacy_find_separator_y(
                rgb_sum, candidate_x, 60, **kwargs
            )
            assert actual == expected
