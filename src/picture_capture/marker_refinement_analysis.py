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


def whiten_illustrations_for_refinement(
    image: Image.Image,
    settings,
    page_index: int,
    *,
    source_image_path: Path | None = None,
) -> Image.Image:
    """Apply the refinement button's opt-in mask to an in-memory image.

    When disabled, return the input unchanged. Reuse mode reads the existing
    PPP and never redetects. Automatic mode must not persist detected polygons:
    the shared masker receives a source path ONLY when reading existing PPP.
    Callers own and close a distinct returned image; the source is never edited.
    """
    if not bool(getattr(settings, "layout_mask_illustrations", False)):
        return image

    from .layout_illustration_mask import mask_large_illustrations_for_layout

    reuse = bool(getattr(settings, "layout_mask_illustrations_use_existing", False))
    if reuse and source_image_path is None:
        raise ValueError("复用已有插图白化需要当前页原图路径，不能忽略 PPP 配置")
    path_kwargs = {"source_image_path": Path(source_image_path)} if reuse else {}
    masked, _stats = mask_large_illustrations_for_layout(
        image, settings,
        profile_page_index=int(page_index),
        **path_kwargs,
    )
    return masked


def whiten_illustrations_for_export(
    image: Image.Image,
    settings,
    page_index: int,
    *,
    source_image_path: Path,
) -> Image.Image:
    """In PPP-reuse mode, a page without illustrations exports unchanged.

    This exception applies ONLY to row export. Existing PPP is still read by
    the shared masker; corrupt/unreadable PPP remains an error, and no detection
    or PPP write occurs on pages that lack a companion file.
    """
    if (bool(getattr(settings, "layout_mask_illustrations", False))
            and bool(getattr(settings, "layout_mask_illustrations_use_existing", False))):
        from .project_storage import ppp_read_path_for_image

        if not ppp_read_path_for_image(Path(source_image_path)).is_file():
            return image
    return whiten_illustrations_for_refinement(
        image, settings, page_index, source_image_path=source_image_path,
    )


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
        analysis = whiten_illustrations_for_refinement(
            analysis, effective, int(page_index),
            source_image_path=source_image_path,
        )

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
