"""Physical owner of page understanding dispatch, optional illustration masking and image lifetime.

The processing facade retains its historical callable and patch seams.  This
module never installs runtime hooks or writes project/PPP/PDIC sidecars.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from ..models import AppSettings
from ..persistence.page_sections import PageSection
from .page_understanding import PageUnderstanding


def understand_page_current(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int,
    page_sections: list[PageSection] | None,
    layout_only: bool = False,
    layout_trace: Any | None = None,
    replay_preview: Any | None = None,
    source_image_path: Path | None = None,
) -> PageUnderstanding | None:
    """Resolve Page Understanding with optional static illustration masking."""
    analysis_image = image
    mask_stats = None
    append_reason = None
    mask_candidates: list[dict[str, Any]] | None = (
        [] if layout_trace is not None else None
    )
    masking_enabled = bool(getattr(settings, "layout_mask_illustrations", False))
    mask_error = None
    if masking_enabled:
        from .illustration_mask import (
            IllustrationMaskStats,
            append_mask_reason,
            mask_large_illustrations_for_layout,
        )

        mask_stats = IllustrationMaskStats()
        append_reason = append_mask_reason
        try:
            analysis_image, mask_stats = mask_large_illustrations_for_layout(
                image,
                settings,
                profile_page_index=int(page_index),
                **({"source_image_path": source_image_path}
                   if source_image_path is not None else {}),
                **({"candidate_debug": mask_candidates}
                   if mask_candidates is not None else {}),
            )
        except Exception as exc:
            if bool(getattr(settings, "layout_mask_illustrations_use_existing", False)):
                raise
            analysis_image = image
            mask_stats = IllustrationMaskStats()
            mask_error = f"{type(exc).__name__}: {exc}"

    if layout_trace is not None:
        # A disabled/no-candidates/no-mask/failure result is still an explicit
        # stage: the user must not infer that masking was skipped silently.
        stats = mask_stats
        layout_trace.add_note(
            "illustration_mask", "Layout 前插图区域检测／白化",
            ("启用后先筛选自动插图候选，只有安全通过的多边形才填白。"
             if masking_enabled else "当前项目已关闭 Layout 前插图掩膜。"),
            details={
                "enabled": masking_enabled,
                "detected": int(stats.detected) if stats else 0,
                "masked": int(stats.masked) if stats else 0,
                "rejected_small": int(stats.rejected_small) if stats else 0,
                "rejected_headlike": int(stats.rejected_headlike) if stats else 0,
                "failure_fallback_to_unmasked": mask_error,
            },
            candidates=mask_candidates,
        )
        if replay_preview is not None and masking_enabled:
            replay_preview("illustration_mask", analysis_image)

    try:
        # Both the layout-only and enriched Page Understanding branches use
        # explicit Physical Layout composition. Legacy installer preparation is
        # no longer part of the normal detection path.
        if layout_only:
            from .core_understanding import understand_layout_core

            understanding = understand_layout_core(
                analysis_image,
                settings,
                page_index=page_index,
                **({"trace": layout_trace} if layout_trace is not None else {}),
            )
        else:
            from .composition import understand_composed_page

            understanding = understand_composed_page(
                analysis_image,
                settings,
                page_index=page_index,
                page_sections=page_sections,
            )
        if append_reason is not None and mask_stats is not None:
            append_reason(understanding, mask_stats)
        return understanding
    except Exception:
        return None
    finally:
        if analysis_image is not image:
            try:
                analysis_image.close()
            except Exception:
                pass
