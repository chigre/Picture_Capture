"""Disposable illustration whitening for explicit refinement of existing PDIC Y.

Do not run Page Understanding, whole-page layout detectors, OCR or extra
denoising here. The existing Profile/geometry and Y-refinement owners remain
authoritative. Illustration whitening only changes an in-memory analysis copy.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from .image_utils import normalize_page_rgb
from .profile_semantics import effective_page_settings, page_template_analysis_image


def prepare_refinement_analysis(
    image: Image.Image,
    settings,
    page_index: int,
    *,
    source_image_path: Path | None = None,
):
    """Return source, Profile settings, and a disposable whitening/template copy.

    Layout illustration masking is opt-in. Reuse mode reads the saved PPP;
    automatic mode may detect illustrations, but MUST NOT write any PPP here.
    Neither mode performs automatic layout parameter estimation or changes PDIC.
    """
    source = normalize_page_rgb(image)
    analysis = source
    try:
        effective = effective_page_settings(settings, source.size, int(page_index))
        if bool(getattr(effective, "layout_mask_illustrations", False)):
            from .layout_illustration_mask import mask_large_illustrations_for_layout

            reuse = bool(getattr(effective, "layout_mask_illustrations_use_existing", False))
            if reuse and source_image_path is None:
                raise ValueError("复用已有插图白化需要当前页原图路径，不能忽略 PPP 配置")
            # The masker writes auto candidates to PPP when given a source path
            # in auto mode. Only pass the path when reading existing PPP.
            path_kwargs = (
                {"source_image_path": Path(source_image_path)} if reuse else {}
            )
            masked, _stats = mask_large_illustrations_for_layout(
                analysis, effective,
                profile_page_index=int(page_index),
                **path_kwargs,
            )
            analysis = masked

        template = page_template_analysis_image(
            analysis, effective, int(page_index),
        )
        if template is not analysis:
            if analysis is not source:
                analysis.close()
            analysis = template
        if analysis is source:
            analysis = source.copy()
        return source, effective, analysis
    except BaseException:
        if analysis is not source:
            analysis.close()
        source.close()
        raise
