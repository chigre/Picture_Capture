from __future__ import annotations

"""Page nominal/curved geometry construction. All historical core hooks
and pickle-visible Geometry/ColumnPath classes are injected at call time.
No raw image pixels or persistence schemas are modified.
"""

from collections.abc import Callable
from typing import Any
from PIL import Image
from ..models import AppSettings


def derive_nominal_geometry_canonical(
    image_width: int, image_height: int, settings: AppSettings, *,
    source_px_fn: Callable[..., int], offsets_fn: Callable[..., list[int]],
    apply_offsets_fn: Callable[..., list[int]], column_path_cls: type,
    geometry_cls: type,
) -> Any:
    """Return nominal geometry with settings used as literal full-resolution pixels."""
    width = max(1, int(image_width))
    height = max(1, int(image_height))
    count = max(1, int(settings.columns))

    left = max(0, source_px_fn(settings.manual_x))
    gutter = max(0, source_px_fn(settings.gutter))
    column_width = max(10, source_px_fn(settings.column_width))
    base_starts = [left + i * (column_width + gutter) for i in range(count)]
    offsets = offsets_fn(settings, count, width)
    starts = apply_offsets_fn(
        base_starts, offsets, gutter=gutter, max_x=width - 1,
    )

    widths: list[int] = []
    for i, start_x in enumerate(starts):
        if i + 1 < len(starts):
            widths.append(max(1, starts[i + 1] - start_x - gutter))
        else:
            widths.append(max(1, width - start_x))

    top = min(height - 1, max(0, source_px_fn(settings.start_y)))
    bottom_setting = source_px_fn(settings.bottom_y)
    if settings.crop_to_bottom_y and bottom_setting > top:
        bottom = min(height, max(top + 1, bottom_setting))
    else:
        bottom = height
    paths = [column_path_cls([(top, x), (bottom, x)]) for x in starts]
    return geometry_cls(starts, widths, top, bottom, paths)

def derive_nominal_geometry(
    image_width: int, image_height: int, settings: AppSettings, *,
    transform_cls: type, derive_canonical_fn: Callable[..., Any],
) -> Any:
    """Return canonical nominal geometry while retaining source mapping metadata."""
    transform = transform_cls(str(getattr(settings, "layout_transform", "identity") or "identity"))
    source_size = (max(1, int(image_width)), max(1, int(image_height)))
    canonical_size = transform.canonical_size(source_size)
    geometry = derive_canonical_fn(*canonical_size, settings)
    geometry.transform = transform
    geometry.source_size = source_size
    return geometry


def derive_geometry_canonical(
    image: Image.Image, settings: AppSettings, *,
    analysis_fn: Callable[..., tuple[Image.Image, float]],
    source_px_fn: Callable[..., int], offsets_fn: Callable[..., list[int]],
    apply_offsets_fn: Callable[..., list[int]], estimate_paths_fn: Callable[..., list[Any]],
    column_path_cls: type, geometry_cls: type,
) -> Any:
    """Build geometry from literal full-resolution pixel settings.

    Image analysis may use a downscaled copy, but configured X/Y values are
    never round-tripped through that analysis scale.
    """
    analysis, analysis_scale = analysis_fn(image)
    analysis_width, analysis_height = analysis.size
    source_width, source_height = image.size
    count = max(1, int(settings.columns))

    left = max(0, source_px_fn(settings.manual_x))
    gutter = max(0, source_px_fn(settings.gutter))
    column_width = max(10, source_px_fn(settings.column_width))
    base_starts = [left + i * (column_width + gutter) for i in range(count)]
    offsets = offsets_fn(settings, count, source_width)
    starts = apply_offsets_fn(
        base_starts, offsets, gutter=gutter, max_x=source_width - 1,
    )

    widths: list[int] = []
    for i, start_x in enumerate(starts):
        if i + 1 < len(starts):
            widths.append(max(1, starts[i + 1] - start_x - gutter))
        else:
            widths.append(max(1, source_width - start_x))

    top = min(source_height - 1, max(0, source_px_fn(settings.start_y)))
    bottom_setting = source_px_fn(settings.bottom_y)
    if settings.crop_to_bottom_y and bottom_setting > top:
        bottom = min(source_height, max(top + 1, bottom_setting))
    else:
        bottom = source_height

    starts_analysis = [
        min(analysis_width - 1, max(0, round(x * analysis_scale)))
        for x in starts
    ]
    widths_analysis = [
        max(1, round(width * analysis_scale)) for width in widths
    ]
    top_analysis = min(
        analysis_height - 1, max(0, round(top * analysis_scale))
    )
    bottom_analysis = min(
        analysis_height, max(top_analysis + 1, round(bottom * analysis_scale))
    )

    if settings.follow_column_deformation:
        paths = estimate_paths_fn(
            analysis,
            analysis_scale,
            starts_analysis,
            widths_analysis,
            top_analysis,
            bottom_analysis,
            settings,
            analysis_scale,
        )
    else:
        paths = [column_path_cls([(top, x), (bottom, x)]) for x in starts]
    return geometry_cls(starts, widths, top, bottom, paths)

def derive_geometry(
    image: Image.Image, settings: AppSettings, *,
    normalize_rgb_fn: Callable[[Image.Image], Image.Image],
    transform_cls: type, derive_canonical_fn: Callable[..., Any],
) -> Any:
    """Build layout geometry in canonical space without changing source pixels."""
    source = normalize_rgb_fn(image)
    transform = transform_cls(str(getattr(settings, "layout_transform", "identity") or "identity"))
    canonical = transform.canonical_image_for_analysis(source)
    geometry = derive_canonical_fn(canonical, settings)
    geometry.transform = transform
    geometry.source_size = source.size
    return geometry
