"""Main workspace quick-settings validation and persistence behavior.

All source pixels, Profile percent/pixel conversions, current app callback
seams and settings fields remain controlled by the owning GUI instance.
"""
from __future__ import annotations
from typing import Any


def apply_quick_settings(self, show_status: bool = True, persist: bool = False, silent_errors: bool = False, *, deps: dict[str, Any]) -> bool:
    LAYOUT_PERCENT_AXES = deps["LAYOUT_PERCENT_AXES"]
    _layout_percent_to_pixels = deps["_layout_percent_to_pixels"]
    normalize_content_font_setting = deps["normalize_content_font_setting"]
    language_effective_settings = deps["language_effective_settings"]
    LENS_MODE_VALUES = deps["LENS_MODE_VALUES"]
    re = deps["re"]
    if getattr(self, "_batch_active", False):
        self.status_var.set("批量任务运行中，参数修改将在任务结束后再进行。")
        return False
    try:
        previous_ocr_language = str(getattr(self.settings, "ocr_language", "") or "")
        original_geometry = {
            name: self._quick_geometry_value(name)
            for name in LAYOUT_PERCENT_AXES
            if name in self.quick_vars
        }
        for name, var in self.quick_vars.items():
            geometry_source = self._quick_geometry_edit_source.get(name, "percent")
            if (
                name in original_geometry
                and geometry_source == "pixel"
                and name in getattr(self, "quick_pixel_vars", {})
            ):
                value = int(round(float(self.quick_pixel_vars[name].get().strip())))
            else:
                value = self.quick_field_casts[name](var.get())
            if name in original_geometry:
                if (
                    geometry_source != "pixel"
                    and self.image is not None
                    and name in LAYOUT_PERCENT_AXES
                ):
                    percent = float(value)
                    if not 0.0 <= percent <= 100.0:
                        raise ValueError(f"{name} 必须在 0–100% 之间。")
                    value = _layout_percent_to_pixels(self.image, name, percent)
                else:
                    value = int(value)
                if value < 0:
                    raise ValueError(f"{name} 不能小于 0。")
                changed = value != original_geometry[name]
                horizontal = not str(
                    getattr(self.settings, "layout_writing_mode", "horizontal-tb") or "horizontal-tb"
                ).startswith("vertical")
                if self.image is not None and horizontal and name == "start_y" and str(
                    getattr(self.settings, "profile_header_mode", "auto") or "auto"
                ) == "present":
                    if value > self.image.height:
                        raise ValueError(f"页眉Y必须在原图 0–{self.image.height} 之间。")
                    if changed:
                        percent = value * 100.0 / max(1, self.image.height)
                        if percent > 35.0:
                            raise ValueError("页眉不能超过原图高度的 35%。")
                        self.settings.profile_header_percent = round(percent, 6)
                elif self.image is not None and horizontal and name == "bottom_y" and str(
                    getattr(self.settings, "profile_footer_mode", "auto") or "auto"
                ) == "present":
                    if value > self.image.height:
                        raise ValueError(f"页尾Y必须在原图 0–{self.image.height} 之间。")
                    if changed:
                        percent = (
                            (self.image.height - value)
                            * 100.0
                            / max(1, self.image.height)
                        )
                        if not 0.0 <= percent <= 35.0:
                            raise ValueError("页尾必须位于原图底部 35% 范围内。")
                        self.settings.profile_footer_percent = round(percent, 6)
                value = int(value)
            if name == "paddle_band_width_ratio" and not 1.0 <= float(value) <= 100.0:
                raise ValueError("候选带宽比例必须在 1–100 之间；100 即原候选带宽。")
            if name == "paddle_separator_safety_px" and not 0 <= int(value) <= 50:
                raise ValueError("Y精修安全空间必须在 0–50 px 之间。")
            if name == "paddle_separator_roi_width_ratio" and not 10.0 <= float(value) <= 100.0:
                raise ValueError("Y精修横向分析范围必须在 10–100% 之间。")
            if name == "right_ratio" and not 1 <= float(value) <= 100:
                raise ValueError("向右比例必须在 1–100% 之间。")
            if name == "main_entry_x_ratio":
                if not 0 <= float(value) <= 125:
                    raise ValueError("词条文本框偏移必须在 0–125% 之间。")
                value = float(value) / 100.0
            if name in {"illustration_outline_width", "illustration_label_border_width", "page_section_width"} and not 1 <= int(value) <= 20:
                raise ValueError("线条/外框粗细必须在 1–20 之间。")
            if name == "illustration_label_font_size" and not 5 <= int(value) <= 200:
                raise ValueError("插图标签字号必须在 5–200 之间。")
            if name == "crop_preview_font_size" and not 5 <= int(value) <= 200:
                raise ValueError("切图预览标签字号必须在 5–200 之间。")
            setattr(self.settings, name, value)
        for font_setting_name in (
            "main_entry_font_family",
            "illustration_label_font_family",
            "crop_preview_font_family",
            "review_entry_font_family",
            "review_simplified_font_family",
        ):
            setattr(
                self.settings,
                font_setting_name,
                normalize_content_font_setting(getattr(self.settings, font_setting_name, "")),
            )
        current_ocr_language = str(getattr(self.settings, "ocr_language", "") or "")
        if current_ocr_language != previous_ocr_language:
            for setting_name, setting_value in language_effective_settings(
                current_ocr_language, self.settings.layout_writing_mode,
            ).items():
                if hasattr(self.settings, setting_name):
                    setattr(self.settings, setting_name, setting_value)
        # Lens always follows the active headword OCR language, including
        # old projects that still carry a historical independent value.
        self.settings.paddle_lens_language = current_ocr_language
        # Diagnostic view flags live only in the UI; never attempt to
        # persist an ad-hoc BooleanVar onto the slotted AppSettings model.
        for name, var in self.quick_bool_vars.items():
            if hasattr(self.settings, name):
                setattr(self.settings, name, bool(var.get()))
        for name, var in getattr(self, "quick_color_vars", {}).items():
            value = str(var.get()).strip()
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise ValueError(f"{name} 不是有效的 #RRGGBB 颜色")
            setattr(self.settings, name, value.lower())
        if not (self.settings.paddle_use_paddleocr or self.settings.paddle_compare_tesseract or self.settings.paddle_enable_lens):
            raise ValueError("OCR引擎至少需要勾选一个。")
        self.settings.paddle_lens_mode = LENS_MODE_VALUES.get(self.lens_mode_var.get(), self.settings.paddle_lens_mode)
        self.settings.hide_overlays = bool(self.hide_var.get())
        self.settings.polygon_mode = bool(self.polygon_var.get())
        if persist: self.save_settings()
        self.sync_quick_settings()
        self.redraw()
        if self.autosave_var.get(): self.toggle_autosave()
        if show_status: self.status_var.set("主界面参数已应用" + ("并保存" if persist else ""))
        return True
    except Exception as exc:
        if not silent_errors:
            self.show_error("参数无效", exc)
        return False
