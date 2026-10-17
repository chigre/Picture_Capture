from __future__ import annotations

"""Small deterministic helpers for runtime benchmark summaries."""

import math
from statistics import mean, median


def timing_summary_ms(values: list[float]) -> dict[str, float | int | None]:
    samples = [float(value) for value in values if math.isfinite(float(value))]
    if not samples:
        return {
            "samples": 0,
            "total": 0.0,
            "mean": None,
            "median": None,
            "p95": None,
            "min": None,
            "max": None,
        }

    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * 0.95) - 1))
    return {
        "samples": len(ordered),
        "total": round(sum(ordered), 3),
        "mean": round(mean(ordered), 3),
        "median": round(median(ordered), 3),
        "p95": round(ordered[p95_index], 3),
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
    }
