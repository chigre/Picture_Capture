from __future__ import annotations

"""Pure overlay, preview, and editor-layout helpers for the main UI."""

from PIL import Image, ImageOps

from .models import AppSettings


def effective_main_overlay_font_size(
    image_width: int, view_scale: float, settings: AppSettings,
) -> int:
    """Return the main overlay font size.

    1400 px displayed page width corresponds to the configured base font size.
    """

    base_size = max(5, int(settings.main_entry_font_size))

    if settings.main_entry_follow_zoom:
        displayed_page_width = max(1.0, image_width * view_scale)
        scale = displayed_page_width / 1400.0
        font_size = round(base_size * scale)
    else:
        font_size = base_size

    return max(5, min(72, font_size))


def scaled_overlay_line_width(value: int | float, overlay_scale: float) -> int:
    """Convert a 100%-image line width to the current canvas display width.

    Main overlay line settings are defined against the image/reference scale.
    Rendering applies exactly one display ratio so Section, column guides,
    headword markers and illustration outlines/borders all respond identically
    when the page is zoomed.
    """
    return max(1, round(max(1.0, float(value)) * max(0.01, float(overlay_scale))))


def review_auto_fit_zoom(
    crop_width: int | float, image_area_width: int | float, fill_ratio: float = 0.99,
) -> float:
    """Scale one proofreading strip to occupy the requested left-pane width."""
    source_width = max(1.0, float(crop_width))
    available_width = max(1.0, float(image_area_width))
    ratio = min(1.0, max(0.01, float(fill_ratio)))
    return max(0.01, available_width * ratio / source_width)


def binary_preview_image(source: Image.Image) -> Image.Image:
    """Create a display-only Otsu black/white preview without mutating source."""
    gray = ImageOps.grayscale(source)
    histogram = gray.histogram()
    total = sum(histogram)
    weighted = sum(i * count for i, count in enumerate(histogram))
    background = 0
    weight_background = 0
    best_variance = -1.0
    threshold = 127
    for value, count in enumerate(histogram):
        weight_background += count
        if not weight_background:
            continue
        weight_foreground = total - weight_background
        if not weight_foreground:
            break
        background += value * count
        mean_background = background / weight_background
        mean_foreground = (weighted - background) / weight_foreground
        variance = weight_background * weight_foreground * (mean_background - mean_foreground) ** 2
        if variance > best_variance:
            best_variance = variance
            threshold = value
    return gray.point(lambda pixel: 255 if pixel > threshold else 0, mode="1").convert("RGB")



def vertical_marker_contact_gap(marker_line_width: int) -> int:
    """Offset from marker centreline so the editor border touches its painted edge."""
    return max(1, (max(1, int(marker_line_width)) + 1) // 2)


def vertical_overlay_layout(
    marker_x: float,
    marker_y: float,
    editor_width: int,
    editor_height: int,
    writing_mode: str,
    *,
    gap: int = 3,
) -> tuple[
    tuple[int, int, int, int],
    tuple[float, float],
    str,
    tuple[float, float],
    str,
]:
    """Return a fixed-size real vertical editor layout around the marker.

    editor_width/editor_height are the actual requested dimensions of the
    vertical Text widget. For vertical-rl the widget stays entirely to the
    left of the marker; vertical-lr is the exact opposite.
    """
    proxy_width = max(1, int(round(editor_width)))
    proxy_height = max(1, int(round(editor_height)))
    gap = max(0, int(gap))
    top = int(round(marker_y))

    if writing_mode == "vertical-rl":
        right = int(round(marker_x - gap))
        left = right - proxy_width
        popup = (float(right), float(top))
        popup_anchor = "ne"
        index = (float(left - 3), float(top))
        index_anchor = "ne"
    elif writing_mode == "vertical-lr":
        left = int(round(marker_x + gap))
        right = left + proxy_width
        popup = (float(left), float(top))
        popup_anchor = "nw"
        index = (float(right + 3), float(top))
        index_anchor = "nw"
    else:
        raise ValueError(f"Not a vertical writing mode: {writing_mode}")

    box = (left, top, right, top + proxy_height)
    return box, popup, popup_anchor, index, index_anchor


def vertical_ocr_menu_layout(
    entry_box: tuple[int, int, int, int],
    menu_width: int,
    writing_mode: str,
    canvas_width: int,
) -> tuple[float, float, str]:
    """Place the OCR selector outside the vertical entry box on the same side."""
    left, top, right, _bottom = entry_box
    menu_width = max(1, int(menu_width))
    if writing_mode == "vertical-rl":
        x = left - 3
        if x - menu_width < 2:
            x = menu_width + 2
        return float(x), float(top), "ne"
    if writing_mode == "vertical-lr":
        x = right + 3
        if x + menu_width > canvas_width - 2:
            x = max(0, canvas_width - menu_width - 2)
        return float(x), float(top), "nw"
    raise ValueError(f"Not a vertical writing mode: {writing_mode}")


def transformed_entry_anchor(
    transform, canonical_x: float, canonical_y: float, column_width: float,
    x_ratio: float, source_size: tuple[int, int], view_scale: float,
) -> tuple[float, float]:
    """Apply the entry offset in canonical space, then map it to the source."""
    source_x, source_y = transform.canonical_to_source_point(
        round(canonical_x + column_width * x_ratio), round(canonical_y), source_size,
    )
    return source_x * view_scale, source_y * view_scale


def horizontal_overlay_layout(
    transform, canonical_x: float, canonical_y: float, column_width: float,
    x_ratio: float, source_size: tuple[int, int], view_scale: float, *, rtl: bool,
) -> tuple[tuple[float, float], str, tuple[float, float], str]:
    """Return mirror-equivalent editor/index anchors for horizontal writing."""
    editor = transformed_entry_anchor(
        transform, canonical_x, canonical_y, column_width, x_ratio,
        source_size, view_scale,
    )
    index_source = transform.canonical_to_source_point(
        round(canonical_x + column_width), round(canonical_y), source_size,
    )
    index = (index_source[0] * view_scale + (-3 if rtl else 3), index_source[1] * view_scale)
    return editor, ("ne" if rtl else "nw"), index, ("ne" if rtl else "nw")


def horizontal_ocr_menu_layout(
    editor_x: float, editor_y: float, editor_width: int, *, rtl: bool,
) -> tuple[float, float, str]:
    """Place the OCR selector outside the editor in its reading direction."""
    if rtl:
        return editor_x - editor_width - 3, editor_y, "ne"
    return editor_x + editor_width + 3, editor_y, "nw"


def entry_index_label_layout(
    editor_x: float,
    editor_y: float,
    editor_width: int,
    editor_height: int,
    *,
    horizontal: bool,
    rtl: bool = False,
    vertical_box: tuple[int, int, int, int] | None = None,
    gap: int = 0,
) -> tuple[float, float, str]:
    """Place the entry sequence label immediately before the editor.

    Horizontal labels respect reading direction (left of LTR, right of RTL).
    Vertical labels sit immediately above the text box because vertical reading
    proceeds from top to bottom.
    """
    gap = max(0, int(gap))
    if horizontal:
        if rtl:
            return float(editor_x + gap), float(editor_y), "nw"
        return float(editor_x - gap), float(editor_y), "ne"
    if vertical_box is None:
        raise ValueError("vertical_box is required for vertical entry labels")
    left, top, right, _bottom = vertical_box
    return float((left + right) / 2.0), float(top - gap), "s"
