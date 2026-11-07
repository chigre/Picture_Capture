"""Source-pixel top, bottom and margin bounds for illustration cropping.

Algorithm owner invoked by the stable processing-core facade. Runtime helpers,
models and transaction writers come from the current caller each invocation.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from PIL import Image
    from ..models import AppSettings
    from ..persistence.page_sections import PageSection


def illustration_crop_bounds_impl(
    image: Image.Image,
    settings: AppSettings | None = None,
    *,
    top_y: int = 0,
    bottom_y: int = 0,
    margin: int = 0,
    page_sections: list[PageSection] | None = None,
    deps: dict[str, Any],
) -> tuple[int, int, int]:
    """Resolve persisted crop settings to current source-image pixels.

    Crop Settings v6 stores distances in canonical reference-page pixels. For
    ordinary horizontal pages canonical V equals source Y. For 90-degree page
    transforms, illustration polygons are still source-space annotations, so
    only isotropic scalar distances such as margin are reused directly;
    transformed whole-entry cropping is handled through canonical geometry.
    A bottom value of 0 remains the physical image-bottom sentinel.
    """
    _source_px = deps["_source_px"]
    LayoutTransform = deps["LayoutTransform"]
    normalize_page_sections = deps["normalize_page_sections"]
    AppSettings = deps["AppSettings"]
    effective = settings or AppSettings()
    transform = LayoutTransform(
        str(getattr(effective, "layout_transform", "identity") or "identity")
    )
    canonical_width, canonical_height = transform.canonical_size(image.size)
    if page_sections:
        effective_sections = normalize_page_sections(page_sections, 0, canonical_height)
        top_canonical = effective_sections[0].top_v
        bottom_canonical = effective_sections[-1].bottom_v
    else:
        top_canonical = _source_px(max(0, int(top_y)))
        bottom_canonical = (
            _source_px(max(0, int(bottom_y)))
            if int(bottom_y) > 0 else 0
        )
    margin_px = max(
        0, _source_px(max(0, int(margin))),
    )
    # Illustration polygons are persisted in source XY. Horizontal layouts are
    # the supported physical top/bottom crop convention; rotated layouts keep
    # the full source-height guard rather than mislabel canonical V as source Y.
    if transform.kind in {"identity", "mirror_x"}:
        top = max(0, min(image.height - 1, top_canonical))
        bottom = (
            max(top + 1, min(image.height, bottom_canonical))
            if bottom_canonical > 0 else image.height
        )
    else:
        top = 0
        bottom = image.height
    return top, bottom, margin_px
