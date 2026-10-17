"""Settings-aware, geometry-only preparation for the explicit refine-lines command.

The existing PDIC supplies every candidate.  This module does not classify
entry/body rows, run OCR, mutate the original image or publish PPP data.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from .image_utils import build_analysis_image, normalize_page_rgb
from .adaptive_denoise import resolve_denoise_strength
from .profile_semantics import effective_page_settings, page_template_analysis_image


def prepare_refinement_analysis(
    image: Image.Image,
    settings,
    page_index: int,
    *,
    source_image_path: Path | None = None,
):
    """Return (original RGB copy, resolved settings, disposable analysis RGB).

    Denoise and masking follow the per-page Profile settings.  Auto-layout
    runs *only* the physical-parameter policy, never Layout Core or semantic
    Page Understanding.  The existing estimator may use its own cache.

    In non-reuse mode the illustration masker must not receive an image path:
    its production entrypoint can otherwise write detected PPP candidates.
    """
    source = normalize_page_rgb(image)
    analysis = None
    try:
        effective = effective_page_settings(settings, source.size, int(page_index))
        # Avoid full-page neighbourhood filtering entirely when the user
        # disabled the shared denoiser (including explicit strength='off').
        analysis = (
            source.copy() if resolve_denoise_strength(effective) == "off"
            else build_analysis_image(source, effective)
        )

        if bool(getattr(effective, "layout_mask_illustrations", False)):
            from .layout_illustration_mask import mask_large_illustrations_for_layout

            reuse = bool(getattr(effective, "layout_mask_illustrations_use_existing", False))
            if reuse and source_image_path is None:
                raise ValueError("复用已有插图白化需要当前页原图路径，不能忽略 PPP 配置")
            kwargs = {"source_image_path": Path(source_image_path)} if reuse else {}
            masked, _stats = mask_large_illustrations_for_layout(
                analysis, effective, profile_page_index=int(page_index), **kwargs,
            )
            if masked is not analysis:
                analysis.close()
                analysis = masked

        if bool(getattr(effective, "ordinary_auto_layout", False)):
            from .dictionary_page_layout_policy import resolve_page_layout_policy

            # Per-field ordinary_auto_* switches are applied in this existing
            # physical policy.  It is not a full Layout/entry-role rebuild.
            effective, _estimate, _applied = resolve_page_layout_policy(
                analysis, effective, page_index=int(page_index),
            )

        template = page_template_analysis_image(analysis, effective, int(page_index))
        if template is not analysis:
            analysis.close()
            analysis = template
        return source, effective, analysis
    except BaseException:
        if analysis is not None:
            analysis.close()
        source.close()
        raise
