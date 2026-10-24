"""Pixel-exact OCR column band unwrapping for straight/curved source columns.

Historical core passes active normalization, PIL and NumPy dependencies.
No source coordinate mapping or sidecar schema is changed.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
from PIL import Image
if TYPE_CHECKING:
    import numpy as np
    from ..models import AppSettings
    from ..processing_core import Geometry


def unwrap_column_band_impl(
    image: Image.Image,
    geometry: "Geometry",
    column: int,
    settings: AppSettings,
    source_width: int | None = None,
    *,
    source_rgb: np.ndarray | None = None,
    np_module: Any,
    normalize_rgb_fn: Any,
    image_class: Any,
) -> tuple[Image.Image, int, int]:
    """Straighten a band following the possibly curved left edge of a column.

    Returns ``(band, source_top, source_left_margin)``. Every band row maps to
    the same source-image Y coordinate, so OCR Y boxes only need an offset when
    converted back to PDIC markers.
    """
    np = np_module
    normalize_page_rgb = normalize_rgb_fn
    Image = image_class
    if source_rgb is None:
        source = np.asarray(normalize_page_rgb(image))
    else:
        source = np.asarray(source_rgb)
        if source.ndim != 3 or source.shape[2] < 3:
            raise ValueError("source_rgb 必须是 H×W×3 的 RGB 数组")
        if source.shape[0] != image.height or source.shape[1] != image.width:
            raise ValueError("source_rgb 尺寸必须与当前原始页面一致，禁止跨页复用")
        if source.shape[2] != 3:
            source = source[:, :, :3]
    band_ratio = max(
        1.0, min(100.0, float(getattr(settings, "paddle_band_width_ratio", 100.0)))
    ) / 100.0
    left_margin = max(0, int(settings.paddle_band_left_margin))
    if source_width is not None:
        # Explicit callers (notably separator refinement) request an exact
        # source width and intentionally bypass the user-facing percentage.
        band_width = max(24, int(source_width))
    else:
        # paddle_band_width_ratio is a percentage of the actual detected
        # column width, not of the historical fixed paddle_band_width.
        # Keep the left safety margin separate from that percentage: 100%
        # means the complete column content plus the configured pixels to its left.
        #
        # The old 600px reference made 60% become 360px on every scan, which
        # silently clipped long CJK headwords and changed meaning with DPI.
        configured_column_width = max(
            1, int(getattr(settings, "column_width", 0) or 0)
        )
        geometry_interval_width = (
            int(geometry.column_widths[column])
            if 0 <= column < len(geometry.column_widths)
            else configured_column_width
        )
        # Geometry's last interval may extend from the final column start all
        # the way to the page edge, so it is only an upper bound here.  The
        # effective per-page settings.column_width is the actual dictionary
        # column width resolved by Profile/layout analysis.
        column_width = max(
            1, min(configured_column_width, max(1, geometry_interval_width))
        )
        content_width = max(1, round(column_width * band_ratio))
        band_width = max(24, content_width + left_margin)
    top = max(0, geometry.top)
    canonical_size = geometry.transform.canonical_size(image.size)
    bottom = min(canonical_size[1], geometry.bottom)
    if geometry.transform.kind != "identity":
        canonical_left = max(0, geometry.column_starts[column] - left_margin)
        canonical_right = min(canonical_size[0], canonical_left + band_width)
        source_box = geometry.transform.canonical_box_to_source(
            (canonical_left, top, canonical_right, bottom), image.size
        )
        return normalize_page_rgb(image).crop(source_box), top, left_margin
    band = np.full((max(1, bottom - top), band_width, 3), 255, dtype=np.uint8)
    for band_y, source_y in enumerate(range(top, bottom)):
        source_x = geometry.x_at(column, source_y) - left_margin
        src_left = max(0, source_x)
        src_right = min(image.width, source_x + band_width)
        if src_right <= src_left:
            continue
        dst_left = src_left - source_x
        dst_right = dst_left + (src_right - src_left)
        band[band_y, dst_left:dst_right] = source[source_y, src_left:src_right]
    return Image.fromarray(band, "RGB"), top, left_margin
