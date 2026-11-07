from __future__ import annotations

"""Pure OCR visual-boundary measurements: ink, runs, ROI and header separator.

The historical OCR core owns the public patch points and injects the current
run detector when computing running-header cutoffs. No candidate decision,
OCR engine state, page cache, or persisted data model lives here.
"""

from collections.abc import Callable
import numpy as np
from ..models import AppSettings
from .headword_models import OCRLine


def ink_ratio(gray: np.ndarray, box: tuple[int, int, int, int]) -> float:
    x0, y0, x1, y1 = box
    y0, y1 = max(0, y0), min(gray.shape[0], y1)
    x0, x1 = max(0, x0), min(gray.shape[1], x1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return float((gray[y0:y1, x0:x1] < 180).mean())


def leading_box(line: OCRLine, matched_chars: int) -> tuple[int, int, int, int]:
    """Approximate the lemma's visual box for a local ink/boldness estimate."""
    x0, y0, x1, y1 = line.box
    if not line.text or x1 <= x0:
        return line.box
    fraction = min(1.0, max(0.16, matched_chars / max(1, len(line.text))))
    right = min(x1, x0 + max(3, round((x1 - x0) * fraction * 1.12)))
    return x0, y0, right, y1


def true_runs(values: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(values):
        if value and start is None:
            start = index
        elif not value and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(values)))
    return runs


def separator_analysis_x_bounds(
    width: int,
    settings: AppSettings,
    pixel_scale: float = 1.0,
) -> tuple[int, int]:
    """Return the left-local X ROI used for separator/boundary analysis.

    Dictionary headwords usually live at the left of a column while definitions
    can run across its full width.  Analysing the whole column lets long text on
    the preceding definition line contaminate a local Y boundary.  The user can
    therefore limit refinement to a percentage of the left side of the column.
    """
    width = max(1, int(width))
    margin = max(0, round(max(0, settings.paddle_separator_column_margin) * pixel_scale))
    margin = min(margin, max(0, width // 4))
    ratio = max(10.0, min(100.0, float(getattr(settings, "paddle_separator_roi_width_ratio", 60.0)))) / 100.0
    usable = max(1, width - margin * 2)
    x0 = margin
    x1 = min(width - margin, x0 + max(16, round(usable * ratio)))
    if x1 - x0 < 16:
        x0, x1 = 0, width
    return int(x0), int(x1)


def header_cutoff(
    gray: np.ndarray, settings: AppSettings, ratio: float, *,
    true_runs_fn: Callable[[np.ndarray], list[tuple[int, int]]] = true_runs,
) -> int:
    """Return band Y below a strong running-header separator, or zero."""
    if not settings.paddle_auto_header_rule or gray.size == 0:
        return 0
    search_height = min(gray.shape[0], max(1, round(settings.paddle_header_search_height * ratio)))
    if search_height <= 1:
        return 0
    dark = gray[:search_height] < 180
    row_ink = dark.mean(axis=1)
    active = row_ink >= min(0.98, max(0.05, settings.paddle_header_rule_ink_ratio))
    runs = true_runs_fn(active)
    if not runs:
        return 0
    # A real horizontal rule should survive on at least one full scan row.
    # Use the last qualifying rule in the top search zone; this handles a
    # double rule without treating the running-header text itself as a rule.
    _, end = runs[-1]
    return min(gray.shape[0], end + max(0, round(settings.paddle_header_rule_margin * ratio)))
