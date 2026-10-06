from __future__ import annotations

"""Runtime hardening for OCR-independent oversized-head evidence.

Two page facts must hold before an oversized glyph is allowed to override an
otherwise-correct physical-indent role:

* the size reference must describe the *observed ordinary rows* on this page,
  not only a possibly underestimated project/fallback character height;
* the oversized object must live at the physical start of its Layout row. A
  large/merged object in the middle of definition text is not a headword merely
  because its bounding box is tall.

The detector also reuses the Layout column-drift helper's analysis-only left
safety band.  This is intentionally done *inside* the guarded detector: the
column-drift installer must never replace this callable, otherwise import order
can silently disable row-front/strong-oversized authorization.
"""

from typing import Any

import numpy as np
from PIL import Image

from .models import AppSettings, Entry


def observed_body_line_reference(layout: Any) -> float:
    """Return a conservative ordinary-row height for large-head comparison."""
    baseline = max(
        8.0,
        float(getattr(layout, "ordinary_line_height", 1.0) or 1.0),
    )
    body_heights: list[float] = []
    all_heights: list[float] = []
    for column in list(getattr(layout, "columns", []) or []):
        for line in list(getattr(column, "lines", []) or []):
            try:
                height = float(getattr(line, "y1")) - float(getattr(line, "y0"))
            except (AttributeError, TypeError, ValueError):
                continue
            if height <= 0:
                continue
            if baseline * 0.42 <= height <= baseline * 2.20:
                all_heights.append(height)
                if str(getattr(line, "role", "body") or "body") == "body":
                    body_heights.append(height)

    samples = body_heights if len(body_heights) >= 8 else all_heights
    if len(samples) < 8:
        return baseline

    values = np.asarray(samples, dtype=float)
    center = float(np.median(values))
    deviation = np.abs(values - center)
    mad = float(np.median(deviation)) if deviation.size else 0.0
    if mad > 0:
        kept = values[deviation <= max(2.0, 3.5 * mad)]
        if kept.size >= 6:
            center = float(np.median(kept))

    return float(max(baseline, min(center, baseline * 1.80)))


def candidate_starts_at_row_front(
    column: Any,
    box: tuple[int, int, int, int],
    line_height: float,
) -> bool:
    """Return whether one candidate belongs to the leading structure of a row."""
    x0, y0, _x1, _y1 = box
    lines = list(getattr(column, "lines", []) or [])
    if not lines:
        return False

    reference = max(8.0, float(line_height))
    nearest = min(
        lines,
        key=lambda line: abs(float(getattr(line, "y0", 0) or 0) - float(y0)),
    )
    row_y0 = float(getattr(nearest, "y0", 0) or 0)
    row_y1 = float(getattr(nearest, "y1", row_y0) or row_y0)
    if not (
        row_y0 - reference * 0.55
        <= float(y0)
        <= row_y1 + reference * 0.35
    ):
        return False

    try:
        first_x = float(getattr(nearest, "first_x", 0) or 0)
    except (TypeError, ValueError):
        first_x = 0.0
    anchor = getattr(nearest, "anchor_x", None)
    try:
        anchor_x = float(anchor) if anchor is not None else None
    except (TypeError, ValueError):
        anchor_x = None

    allowed_forward = reference * 2.50
    if anchor_x is not None and anchor_x >= first_x:
        allowed_forward = max(
            allowed_forward,
            (anchor_x - first_x) + reference * 0.85,
        )
    return bool(
        float(x0) >= first_x - reference * 0.45
        and float(x0) <= first_x + allowed_forward
    )


def detect_ordinary_large_head_entries_guarded(
    image: Image.Image,
    understanding: Any,
    settings: AppSettings,
) -> list[Entry]:
    """Detect only row-leading oversized CJK heads with a page-observed scale."""
    from . import ordinary_large_head_evidence as base
    from .layout_column_drift import _analysis_left_for_column

    if not base._uses_cjk_large_heads(settings):
        return []

    layout = understanding.layout
    canonical = layout.transform.canonical_image_for_analysis(image.convert("RGB"))
    try:
        gray_page = np.asarray(canonical.convert("L"), dtype=np.uint8)
        line_height = observed_body_line_reference(layout)
        found: list[Entry] = []
        columns = list(getattr(layout, "columns", []) or [])
        top = max(0, int(getattr(layout, "body_top", 0) or 0))
        bottom = min(
            gray_page.shape[0],
            int(getattr(layout, "body_bottom", gray_page.shape[0]) or gray_page.shape[0]),
        )

        for position, column in enumerate(columns):
            semantic_left = max(0, int(getattr(column, "left", 0) or 0))
            semantic_right = min(
                gray_page.shape[1],
                int(getattr(column, "right", semantic_left + 1) or semantic_left + 1),
            )
            analysis_left = _analysis_left_for_column(columns, position, line_height)
            if semantic_right <= analysis_left or bottom <= top:
                continue

            gray = gray_page[top:bottom, analysis_left:semantic_right]
            if gray.size == 0:
                continue
            ink = gray <= base._otsu(gray)
            local_shift = int(analysis_left - semantic_left)

            for raw_box in base._candidate_boxes(ink, line_height):
                x0, y0, x1, y1 = raw_box
                # Candidate X is local to the widened analysis band. Convert it
                # back to semantic-column-local coordinates before comparing it
                # with LayoutLine.first_x / anchor_x.
                semantic_box = (
                    int(x0 + local_shift),
                    int(y0),
                    int(x1 + local_shift),
                    int(y1),
                )
                if not candidate_starts_at_row_front(column, semantic_box, line_height):
                    continue

                height = float(y1 - y0)
                canonical_y = top + int(y0)
                source_x, source_y = layout.transform.canonical_to_source_point(
                    semantic_left,
                    canonical_y,
                    layout.source_size,
                )
                found.append(Entry(
                    word="",
                    x=int(source_x),
                    y=int(source_y),
                    confidence=min(
                        0.995,
                        max(0.90, height / max(1.0, line_height * 2.5)),
                    ),
                    ocr_source="ordinary_large_head_evidence",
                    issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
                    ocr_visual_run_height=height,
                    ocr_line_height_reference=line_height,
                    ocr_leading_height_ratio=height / max(1.0, line_height),
                    ocr_single_cjk=True,
                    ocr_oversized_cjk=True,
                ))
    finally:
        try:
            canonical.close()
        except Exception:
            pass

    found.sort(key=lambda item: (item.x, item.y))
    deduped: list[Entry] = []
    tolerance = max(4, round(line_height * 0.80))
    for entry in found:
        if any(
            abs(entry.x - prior.x) <= tolerance
            and abs(entry.y - prior.y) <= tolerance
            for prior in deduped
        ):
            continue
        deduped.append(entry)
    return deduped


def install_ordinary_large_head_runtime() -> None:
    """Install before Layout Core imports the detector callable by value."""
    from . import ordinary_large_head_evidence as base

    if bool(getattr(base, "_row_front_runtime_installed", False)):
        return
    base.detect_ordinary_large_head_entries = detect_ordinary_large_head_entries_guarded
    base._row_front_runtime_installed = True


__all__ = [
    "candidate_starts_at_row_front",
    "detect_ordinary_large_head_entries_guarded",
    "install_ordinary_large_head_runtime",
    "observed_body_line_reference",
]
