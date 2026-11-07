"""Piecewise column left-edge anchor tracking in original-image coordinates.

The core supplies the live adaptive-mask, geometry, tracking policy, NumPy and
persistence class collaborators at invocation. No ColumnPath identity is moved.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
from PIL import Image
if TYPE_CHECKING:
    from ..models import AppSettings
    from ..processing_core import ColumnPath


def estimate_column_paths(
    analysis: Image.Image,
    scale: float,
    starts_analysis: list[int],
    widths_analysis: list[int],
    top_analysis: int,
    bottom_analysis: int,
    settings: AppSettings,
    geometry_to_analysis: float,
    *, deps: dict[str, Any],
) -> list[ColumnPath]:
    """Track each column's left text edge with piecewise-linear anchors.

    The legacy VB program estimated a top point, a lower point and one slope.
    Here each vertical block contributes an anchor, which also follows local
    stretching or gentle curvature. Sparse/uncertain blocks inherit the
    nearest reliable position.
    """
    _source_px = deps["_source_px"]
    _adaptive_dark_mask = deps["_adaptive_dark_mask"]
    _COLUMN_TRACK_ADAPTIVE_BLOCK = deps["_COLUMN_TRACK_ADAPTIVE_BLOCK"]
    _COLUMN_TRACK_ADAPTIVE_C = deps["_COLUMN_TRACK_ADAPTIVE_C"]
    _column_tracking_dimensions = deps["_column_tracking_dimensions"]
    _smooth_track = deps["_smooth_track"]
    ColumnPath = deps["ColumnPath"]
    np = deps["np"]
    ImageOps = deps["ImageOps"]
    if not settings.follow_column_deformation:
        return [
            ColumnPath([(round(top_analysis / scale), round(x / scale)),
                        (round(bottom_analysis / scale), round(x / scale))])
            for x in starts_analysis
        ]

    body_indent = _source_px(settings.body_indent)
    dark = _adaptive_dark_mask(
        ImageOps.grayscale(analysis),
        max(3, round(_COLUMN_TRACK_ADAPTIVE_BLOCK * geometry_to_analysis)),
        _COLUMN_TRACK_ADAPTIVE_C,
    )
    _height, width = dark.shape
    body_height = max(1, int(bottom_analysis) - int(top_analysis))
    paths: list[ColumnPath] = []

    for nominal_x, column_width in zip(starts_analysis, widths_analysis):
        # Search range follows the actual current-page column width instead of
        # an absolute source-pixel constant, so the same setting survives DPI
        # changes and page-specific layout detection.
        radius, block_height, stable_step = _column_tracking_dimensions(
            column_width, body_height, settings
        )
        search_left = max(0, nominal_x - radius)
        search_right = min(
            width,
            nominal_x + radius + max(6, round(body_indent * geometry_to_analysis * 0.5)),
        )
        anchors_y: list[int] = []
        raw_x: list[int | None] = []
        for y0 in range(top_analysis, bottom_analysis, block_height):
            y1 = min(bottom_analysis, y0 + block_height)
            anchors_y.append((y0 + y1) // 2)
            region = dark[y0:y1, search_left:search_right]
            if region.size == 0:
                raw_x.append(None)
                continue
            # Ignore near-continuous dark rules or scan borders. Ordinary
            # letter strokes occupy only a minority of rows in a block.
            rule_columns = region.mean(axis=0) > 0.45
            if rule_columns.any():
                expanded_rules = rule_columns.copy()
                expanded_rules[1:] |= rule_columns[:-1]
                expanded_rules[:-1] |= rule_columns[1:]
                region = region.copy()
                region[:, expanded_rules] = False
            # Require two dark pixels in a three-pixel horizontal neighborhood
            # so isolated dust does not define a false left edge.
            if region.shape[1] >= 3:
                sturdy = (
                    region[:, :-2].astype(np.uint8)
                    + region[:, 1:-1].astype(np.uint8)
                    + region[:, 2:].astype(np.uint8)
                ) >= 2
                offset = 1
            else:
                sturdy = region
                offset = 0
            valid_rows = sturdy.any(axis=1)
            if int(valid_rows.sum()) < max(3, round((y1 - y0) * 0.025)):
                raw_x.append(None)
                continue
            first_ink = sturdy.argmax(axis=1)[valid_rows] + search_left + offset
            candidate = round(float(np.percentile(first_ink, 12)))
            candidate = min(nominal_x + radius, max(nominal_x - radius, candidate))
            raw_x.append(candidate)

        reliable = [value for value in raw_x if value is not None]
        if not reliable:
            filled = [nominal_x for _ in raw_x]
        else:
            filled: list[int] = []
            for index, value in enumerate(raw_x):
                if value is not None:
                    filled.append(value)
                    continue
                nearest = min(
                    (j for j, candidate in enumerate(raw_x) if candidate is not None),
                    key=lambda j: abs(j - index),
                )
                filled.append(int(raw_x[nearest]))  # type: ignore[arg-type]
        # Max local movement is a slope-like percentage of the current block
        # height.  This keeps the accepted geometric tilt invariant when the
        # user changes block height or scans at another resolution.
        filled = _smooth_track(
            filled, stable_step, nominal_x=int(nominal_x),
        )
        source_points = [
            (round(y / scale), round(x / scale)) for y, x in zip(anchors_y, filled)
        ]
        source_top = round(top_analysis / scale)
        source_bottom = round(bottom_analysis / scale)
        if not source_points:
            source_points = [(source_top, round(nominal_x / scale)),
                             (source_bottom, round(nominal_x / scale))]
        else:
            source_points.insert(0, (source_top, source_points[0][1]))
            source_points.append((source_bottom, source_points[-1][1]))
        paths.append(ColumnPath(source_points))
    return paths
