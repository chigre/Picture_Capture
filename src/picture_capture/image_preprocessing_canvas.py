from __future__ import annotations

"""Final preprocessing canvas geometry helpers."""

from .image_preprocessing_models import OutputCanvasInfo, PreprocessAnalysis


def _normalize_canvas_alignment(value: str, *, axis: str) -> str:
    value = str(value or "").strip().lower()
    if axis == "x":
        return value if value in {"left", "center", "right"} else "center"
    return value if value in {"top", "center", "bottom"} else "top"


def output_canvas_info(
    analysis: PreprocessAnalysis,
    *,
    enabled: bool = False,
    mode: str = "batch_max",
    requested_width: int = 0,
    requested_height: int = 0,
    canvas_width: int | None = None,
    canvas_height: int | None = None,
    margin_top: int = 0,
    margin_bottom: int = 0,
    margin_left: int = 0,
    margin_right: int = 0,
    align_x: str = "center",
    align_y: str = "top",
) -> OutputCanvasInfo:
    x0, y0, x1, y1 = analysis.crop_box
    content_width = max(1, int(x1) - int(x0))
    content_height = max(1, int(y1) - int(y0))
    align_x = _normalize_canvas_alignment(align_x, axis="x")
    align_y = _normalize_canvas_alignment(align_y, axis="y")
    mode = str(mode or "batch_max").strip().lower()
    if mode not in {"batch_max", "custom"}:
        mode = "batch_max"

    margin_top = max(0, int(margin_top))
    margin_bottom = max(0, int(margin_bottom))
    margin_left = max(0, int(margin_left))
    margin_right = max(0, int(margin_right))

    if not enabled:
        width = content_width
        height = content_height
        margin_top = margin_bottom = margin_left = margin_right = 0
        body_box = (0, 0, width, height)
        paste_x = 0
        paste_y = 0
    else:
        minimum_width = content_width + margin_left + margin_right
        minimum_height = content_height + margin_top + margin_bottom
        width = max(
            minimum_width,
            int(canvas_width or requested_width or minimum_width),
        )
        height = max(
            minimum_height,
            int(canvas_height or requested_height or minimum_height),
        )
        body_x0 = margin_left
        body_y0 = margin_top
        body_x1 = max(body_x0, width - margin_right)
        body_y1 = max(body_y0, height - margin_bottom)
        body_box = (body_x0, body_y0, body_x1, body_y1)
        body_width = max(1, body_x1 - body_x0)
        body_height = max(1, body_y1 - body_y0)

        if align_x == "left":
            paste_x = body_x0
        elif align_x == "right":
            paste_x = body_x1 - content_width
        else:
            paste_x = body_x0 + (body_width - content_width) // 2
        if align_y == "top":
            paste_y = body_y0
        elif align_y == "bottom":
            paste_y = body_y1 - content_height
        else:
            paste_y = body_y0 + (body_height - content_height) // 2

    return OutputCanvasInfo(
        enabled=bool(enabled),
        mode=mode,
        requested_width=max(0, int(requested_width)),
        requested_height=max(0, int(requested_height)),
        width=width,
        height=height,
        margin_top=margin_top,
        margin_bottom=margin_bottom,
        margin_left=margin_left,
        margin_right=margin_right,
        body_box=tuple(int(value) for value in body_box),
        align_x=align_x,
        align_y=align_y,
        content_box=(
            int(paste_x), int(paste_y),
            int(paste_x + content_width), int(paste_y + content_height),
        ),
        expanded_width=bool(
            enabled
            and width > max(0, int(requested_width))
            and mode == "custom"
        ),
        expanded_height=bool(
            enabled
            and height > max(0, int(requested_height))
            and mode == "custom"
        ),
    )


# Preserve historical callable module paths for external pickle/debug tooling.
_normalize_canvas_alignment.__module__ = "picture_capture.image_preprocessing"
output_canvas_info.__module__ = "picture_capture.image_preprocessing"
