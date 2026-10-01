from __future__ import annotations

"""Main-canvas preview for the exact crops sent to entry OCR.

The preview is deliberately visualization-only.  It calls the same canonical
``entry_ocr_crop_box`` helper used by 【仅OCR】, then converts that canonical box
back to source-image coordinates before drawing it on the canvas.
"""

from typing import Any, Iterable
import tkinter as tk
from tkinter import ttk

from .entry_classification import get_entry_classification
from .entry_ocr_crop import entry_ocr_crop_box


REGULAR_COLOR = "#2B7FFF"
OVERSIZED_COLOR = "#F08C00"
ACTIVE_COLOR = "#FF2D55"


def _walk_widgets(root: Any) -> Iterable[Any]:
    try:
        children = list(root.winfo_children())
    except Exception:
        return []
    result: list[Any] = []
    for child in children:
        result.append(child)
        result.extend(_walk_widgets(child))
    return result


def _find_display_row(app: Any) -> Any | None:
    """Return the row that already contains the 【显示标尺】 toggle."""
    for widget in _walk_widgets(app):
        try:
            if str(widget.cget("text") or "") == "显示标尺":
                return widget.master
        except Exception:
            continue
    return None


def _active_review_entry(app: Any) -> tuple[int, int] | None:
    target = getattr(app, "_review_entry_highlight_target", None)
    if not isinstance(target, tuple) or len(target) != 3:
        return None
    try:
        page_index, x, y = (int(target[0]), int(target[1]), int(target[2]))
        if page_index != int(getattr(app, "current_index", -1)):
            return None
        return x, y
    except (TypeError, ValueError):
        return None


def _is_active_entry(entry: Any, target: tuple[int, int] | None) -> bool:
    if target is None:
        return False
    return abs(int(entry.x) - target[0]) <= 2 and abs(int(entry.y) - target[1]) <= 2


def install_ocr_crop_preview(app_module: Any) -> None:
    """Add 【OCR区域预览】 and draw the exact marker-OCR crop rectangles."""
    if getattr(app_module, "_ocr_crop_preview_installed", False):
        return

    App = app_module.PictureCaptureApp
    original_init = App.__init__
    original_redraw = App.redraw

    def draw_preview(self) -> None:
        self.canvas.delete("ocr-crop-preview")
        self.canvas.delete("ocr-crop-preview-label")

        var = getattr(self, "ocr_crop_preview_var", None)
        if var is None or not bool(var.get()):
            return
        if getattr(self, "image", None) is None or not list(getattr(self, "entries", []) or []):
            return
        try:
            if bool(self._preprocess_mode_active()):
                return
        except Exception:
            pass

        try:
            from . import processing as processing_module

            source, effective, analysis_source, geometry = processing_module._page_geometry_context(
                self.image,
                self.settings,
                int(getattr(self, "current_index", 0) or 0),
            )
            canonical = geometry.transform.canonical_image_for_analysis(analysis_source)
            canonical_size = canonical.size
        except Exception:
            return

        scale = max(0.01, float(getattr(self, "view_scale", 1.0) or 1.0))
        engine = str(getattr(effective, "ocr_engine", "") or "").strip().lower()
        engine_label = "PaddleOCR" if engine == "paddleocr" else "Tesseract"
        active_target = _active_review_entry(self)

        for entry in list(getattr(self, "entries", []) or []):
            try:
                canonical_box = entry_ocr_crop_box(
                    entry,
                    geometry,
                    effective,
                    canonical_size,
                )
                source_box = geometry.transform.canonical_box_to_source(
                    canonical_box,
                    geometry.source_size or source.size,
                )
                x0, y0, x1, y1 = [int(value) for value in source_box]
                meta = get_entry_classification(entry)
            except Exception:
                continue

            active = _is_active_entry(entry, active_target)
            oversized = str(meta.entry_scale) == "oversized"
            color = ACTIVE_COLOR if active else (OVERSIZED_COLOR if oversized else REGULAR_COLOR)
            width = 4 if active else 2
            dash = () if active else ((7, 3) if oversized else (4, 3))

            dx0, dy0, dx1, dy1 = [
                float(value) * scale for value in (x0, y0, x1, y1)
            ]
            rectangle_kwargs: dict[str, Any] = {
                "outline": color,
                "width": width,
                "tags": ("ocr-crop-preview",),
            }
            if dash:
                rectangle_kwargs["dash"] = dash
            self.canvas.create_rectangle(dx0, dy0, dx1, dy1, **rectangle_kwargs)

            # Keep labels compact for all rows; expose full provenance on the
            # actively proofread row so the page does not become text-heavy.
            short_scale = "大" if oversized else "普"
            label = f"OCR-{short_scale}"
            if active:
                source_label = str(meta.entry_source or "unknown")
                label = f"{label}｜{source_label}｜{engine_label}"
            self.canvas.create_text(
                dx0 + 3,
                dy0 + 2,
                anchor="nw",
                text=label,
                fill=color,
                tags=("ocr-crop-preview-label",),
            )

        try:
            self.canvas.tag_raise("ocr-crop-preview")
            self.canvas.tag_raise("ocr-crop-preview-label")
        except Exception:
            pass

    def redraw(self, *args, **kwargs):
        result = original_redraw(self, *args, **kwargs)
        try:
            draw_preview(self)
        except Exception:
            # A diagnostic overlay must never prevent the normal page redraw.
            pass
        return result

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.ocr_crop_preview_var = tk.BooleanVar(value=False)
        row = _find_display_row(self)
        if row is not None:
            checkbox = ttk.Checkbutton(
                row,
                text="OCR区域预览",
                variable=self.ocr_crop_preview_var,
                command=self.redraw,
            )
            checkbox.pack(side="left", padx=(10, 0))
            self.ocr_crop_preview_checkbox = checkbox
            attach_tooltip = getattr(self, "_attach_tooltip", None)
            if callable(attach_tooltip):
                try:
                    attach_tooltip(
                        checkbox,
                        "显示【仅OCR】真正送入OCR引擎的裁剪区域。蓝框=普通词条，橙框=大字头；校对当前词条用红框高亮。",
                    )
                except Exception:
                    pass

    App.__init__ = init
    App.redraw = redraw
    App._draw_ocr_crop_preview = draw_preview
    app_module._ocr_crop_preview_installed = True


__all__ = ["install_ocr_crop_preview"]
