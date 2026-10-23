"""Render reviewed crops and encode exports with explicit call-time operations."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from .models import OutputCanvasInfo, PreprocessAnalysis

PREVIEW_YELLOW = (255, 225, 110, 94)
PREVIEW_OUTLINE = (218, 164, 24, 255)


def overlay_excluded_regions(
    image: Image.Image,
    crop_box: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int, int] = PREVIEW_YELLOW,
    outline: tuple[int, int, int, int] = PREVIEW_OUTLINE,
    normalizer: Callable,
) -> Image.Image:
    base = normalizer(image).convert("RGBA")
    width, height = base.size
    x0, y0, x1, y1 = (
        max(0, min(width, int(crop_box[0]))),
        max(0, min(height, int(crop_box[1]))),
        max(0, min(width, int(crop_box[2]))),
        max(0, min(height, int(crop_box[3]))),
    )
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    if y0 > 0:
        draw.rectangle((0, 0, width, y0), fill=fill)
    if y1 < height:
        draw.rectangle((0, y1, width, height), fill=fill)
    if x0 > 0 and y1 > y0:
        draw.rectangle((0, y0, x0, y1), fill=fill)
    if x1 < width and y1 > y0:
        draw.rectangle((x1, y0, width, y1), fill=fill)
    draw.rectangle((x0, y0, max(x0, x1 - 1), max(y0, y1 - 1)), outline=outline, width=3)
    return Image.alpha_composite(base, overlay).convert("RGB")


def review_image(
    image: Image.Image, analysis: PreprocessAnalysis, *, geometry_renderer: Callable, overlay_renderer: Callable
) -> Image.Image:
    corrected = geometry_renderer(image, analysis)
    return overlay_renderer(corrected, analysis.crop_box)


def processed_image(image: Image.Image, analysis: PreprocessAnalysis, *, geometry_renderer: Callable) -> Image.Image:
    corrected = geometry_renderer(image, analysis)
    return corrected.crop(analysis.crop_box)


def processed_image_with_canvas(
    image: Image.Image,
    analysis: PreprocessAnalysis,
    canvas: OutputCanvasInfo | None = None,
    *,
    content_renderer: Callable,
    canvas_info_factory: Callable,
) -> Image.Image:
    content = content_renderer(image, analysis)
    if canvas is None or not canvas.enabled:
        return content
    # Never rescale the retained scan just to make it fit. The batch export
    # resolves a canvas at least as large as every content crop; this local
    # guard keeps direct callers safe as well.
    width = max(
        int(canvas.width),
        content.width + canvas.margin_left + canvas.margin_right,
    )
    height = max(
        int(canvas.height),
        content.height + canvas.margin_top + canvas.margin_bottom,
    )
    if width != canvas.width or height != canvas.height:
        canvas = canvas_info_factory(
            analysis,
            enabled=True,
            mode=canvas.mode,
            requested_width=canvas.requested_width,
            requested_height=canvas.requested_height,
            canvas_width=width,
            canvas_height=height,
            margin_top=canvas.margin_top,
            margin_bottom=canvas.margin_bottom,
            margin_left=canvas.margin_left,
            margin_right=canvas.margin_right,
            align_x=canvas.align_x,
            align_y=canvas.align_y,
        )
    output = Image.new("RGB", (width, height), "white")
    output.paste(content, (canvas.content_box[0], canvas.content_box[1]))
    return output


def save_review_preview(
    page: Path, analysis: PreprocessAnalysis, destination: Path, *, max_long_side: int = 1400, review_renderer: Callable
) -> Path:
    with Image.open(page) as opened:
        preview = review_renderer(opened, analysis)
    scale = min(1.0, max(320, int(max_long_side)) / max(preview.size))
    if scale < 1.0:
        preview = preview.resize(
            (max(1, round(preview.width * scale)), max(1, round(preview.height * scale))),
            Image.Resampling.LANCZOS,
        )
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    preview.save(destination, format="JPEG", quality=88, optimize=True)
    return destination


def save_processed_page(
    page: Path,
    analysis: PreprocessAnalysis,
    destination: Path,
    *,
    canvas: OutputCanvasInfo | None = None,
    canvas_renderer: Callable,
) -> Path:
    with Image.open(page) as opened:
        result = canvas_renderer(opened, analysis, canvas)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    suffix = destination.suffix.casefold()
    if suffix in {".jpg", ".jpeg"}:
        result.save(destination, quality=95, subsampling=0)
    elif suffix in {".tif", ".tiff"}:
        result.save(destination, compression="tiff_lzw")
    else:
        result.save(destination)
    return destination
