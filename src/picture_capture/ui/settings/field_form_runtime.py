"""Settings form controls, grouped parameter rows and validated saving.

SettingsDialog keeps the original class APIs; this module holds their full
implementations and obtains runtime-patchable globals from its caller.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    import tkinter as tk
    import tkinter.ttk as ttk


def setting_widget(self, parent: ttk.Frame, name: str, deps: dict[str, Any]) -> tk.Widget:
    ttk = deps["ttk"]
    tk = deps["tk"]
    font = deps["font"]
    PROJECT_LANGUAGE_CODES = deps["PROJECT_LANGUAGE_CODES"]
    AUTO_FONT_FAMILY = deps["AUTO_FONT_FAMILY"]
    _settings_color_ui = deps["_settings_color_ui"]
    var = self._setting_var(name)
    choices = self.SETTING_CHOICES.get(name)
    if choices:
        return ttk.Combobox(
            parent, textvariable=var, values=tuple(choices.keys()),
            state="readonly", width=26,
        )
    if name in {"dictionary_index_language", "dictionary_content_language"}:
        return ttk.Combobox(
            parent, textvariable=var, values=PROJECT_LANGUAGE_CODES,
            state="readonly", width=26,
        )
    if name == "ocr_language":
        widget = ttk.Combobox(
            parent, textvariable=var, values=self.OCR_LANGUAGES,
            state="normal", width=26,
        )
        widget.bind("<<ComboboxSelected>>", lambda _e: self._refresh_sort_choices())
        widget.bind("<FocusOut>", lambda _e: self._refresh_sort_choices())
        return widget
    if name in {"main_entry_font_family", "review_entry_font_family", "ref_box_font_family"}:
        families = (
            AUTO_FONT_FAMILY,
            *tuple(sorted((f for f in font.families() if not f.startswith("@")), key=str.casefold)),
        )
        return ttk.Combobox(
            parent, textvariable=var, values=families, state="normal", width=26,
        )
    if name == "wordslist_path":
        box = ttk.Frame(parent)
        box.columnconfigure(0, weight=1)
        ttk.Entry(box, textvariable=var, width=28).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            box, text="浏览…", command=lambda v=var: self._browse_wordslist_setting(v)
        ).grid(row=0, column=1, padx=(5, 0))
        return box
    if name in self.SETTING_SPIN:
        lower, upper, increment = self.SETTING_SPIN[name]
        return ttk.Spinbox(
            parent,
            textvariable=var,
            from_=lower,
            to=upper,
            increment=increment,
            width=18,
            justify="left",
        )
    if name == "layout_writing_mode":
        return ttk.Combobox(
            parent, textvariable=var,
            values=("horizontal-tb", "vertical-rl", "vertical-lr"),
            state="readonly", width=26,
        )
    if name == "layout_text_direction":
        return ttk.Combobox(
            parent, textvariable=var, values=("ltr", "rtl"),
            state="readonly", width=26,
        )
    if name == "layout_columns_policy":
        return ttk.Combobox(
            parent, textvariable=var, values=("detect", "fixed"),
            state="readonly", width=26,
        )
    if name == "layout_column_separator_mode":
        return ttk.Combobox(
            parent, textvariable=var, values=("auto", "present", "absent"),
            state="readonly", width=26,
        )
    if name == "layout_transform":
        return ttk.Entry(parent, textvariable=var, width=28, state="readonly")
    return (_settings_color_ui.make_color_widget(parent, var)
            if name.endswith("_color") else ttk.Entry(parent, textvariable=var, width=28))


def add_setting_group(
    self,
    parent: ttk.Frame,
    title: str,
    names: tuple[str, ...] | list[str],
    *,
    intro: str = "",
    help_images: bool = False,
    single_line_labels: bool = False,
    deps: dict[str, Any],
) -> ttk.LabelFrame:
    ttk = deps["ttk"]
    font = deps["font"]
    group = ttk.LabelFrame(parent, text=title, padding=(12, 9))
    group.pack(fill="x", pady=(0, 10))
    group.columnconfigure(1, weight=1)
    if single_line_labels and names:
        label_font = font.nametofont("TkDefaultFont")
        longest_label_width = max(
            label_font.measure(
                f"{self.SETTING_LABELS.get(name, self._field_meta.get(name, (name, str))[0])}："
            )
            for name in names
        )
        group.columnconfigure(0, minsize=longest_label_width + 4)
    row = 0
    if intro:
        intro_label = ttk.Label(
            group, text=intro, foreground="#5f6670", justify="left",
        )
        intro_label.grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=(0, 8)
        )
        self._bind_responsive_labels(
            group, intro_label, horizontal_padding=24, min_wrap=150
        )
        row += 1
    for name in names:
        label = self.SETTING_LABELS.get(name, self._field_meta.get(name, (name, str))[0])
        label_widget = ttk.Label(
            group,
            text=f"{label}：",
            justify="right",
            anchor="e",
            wraplength=0 if single_line_labels else 180,
        )
        label_widget.grid(row=row, column=0, sticky="e", padx=(0, 10), pady=5)

        control = ttk.Frame(group)
        control.grid(row=row, column=1, sticky="ew", pady=4)
        control.columnconfigure(0, weight=1)
        widget = self._setting_widget(control, name)
        widget.grid(row=0, column=0, sticky="ew")
        unit = self.SETTING_UNITS.get(name, "")
        if unit:
            ttk.Label(control, text=unit, foreground="#70757d").grid(
                row=0, column=1, sticky="w", padx=(6, 0)
            )

        info = ttk.Label(group, text="ⓘ", foreground="#6b7280", cursor="hand2")
        info.grid(row=row, column=2, sticky="w", padx=(8, 0))
        callback = lambda n=name, hi=help_images: self._show_setting_help(
            n, show_layout_image=hi
        )
        self._bind_help_widget(label_widget, callback)
        self._bind_help_widget(control, callback)
        self._bind_help_widget(info, callback)
        info.bind(
            "<Button-1>",
            lambda _event, n=name, hi=help_images: self._show_setting_help(
                n, show_layout_image=hi
            ),
            add="+",
        )

        row += 1
    return group


def save_settings(self, *, close: bool = True, show_errors: bool = True, deps: dict[str, Any]) -> bool:
    _settings_lifecycle_ui = deps["_settings_lifecycle_ui"]
    _settings_color_ui = deps["_settings_color_ui"]
    _column_percent_to_pixels = deps["_column_percent_to_pixels"]
    LAYOUT_PERCENT_AXES = deps["LAYOUT_PERCENT_AXES"]
    _layout_percent_to_pixels = deps["_layout_percent_to_pixels"]
    DETECTION_VALUES = deps["DETECTION_VALUES"]
    OCR_ENGINE_VALUES = deps["OCR_ENGINE_VALUES"]
    LENS_MODE_VALUES = deps["LENS_MODE_VALUES"]
    language_effective_settings = deps["language_effective_settings"]
    normalize_content_font_setting = deps["normalize_content_font_setting"]
    parse_custom_order = deps["parse_custom_order"]
    parse_headword_filter_rules = deps["parse_headword_filter_rules"]
    settings_path = deps["settings_path"]
    write_project_profile = deps["write_project_profile"]
    project_profile_path = deps["project_profile_path"]
    headword_filter_rules_path = deps["headword_filter_rules_path"]
    HEADWORD_FILTER_RULES_FILENAME = deps["HEADWORD_FILTER_RULES_FILENAME"]
    messagebox = deps["messagebox"]
    try:
        _settings_lifecycle_ui.validate_projection_width(self.vars)
        _settings_lifecycle_ui.validate_separator_gap_controls(self.vars)
        _settings_lifecycle_ui.validate_ref_box_controls(self.vars)
        _settings_color_ui.validate_color_controls(self.vars)
        previous_language = str(getattr(self.parent.settings, "ocr_language", "") or "")
        previous_backend = {
            name: getattr(self.parent.settings, name, None)
            for name in (
                "paddle_language", "tesseract_language",
                "paddle_tesseract_psm", "paddle_use_textline_orientation",
            )
        }
        for name, var in self.vars.items():
            value = var.get()
            if name in self.SETTING_CHOICES:
                raw_value = self.SETTING_CHOICES[name].get(str(value), str(value))
                cast = self._casts.get(name, str)
                setattr(self.parent.settings, name, cast(raw_value))
            elif name in self._casts:
                if name == "paddle_left_tolerance":
                    percent = float(value)
                    if not 0.0 <= percent <= 100.0:
                        raise ValueError("词头左缘容差必须在 0–100% 单栏宽之间。")
                    setattr(
                        self.parent.settings,
                        name,
                        _column_percent_to_pixels(self.parent.settings, percent),
                    )
                elif name in LAYOUT_PERCENT_AXES and self.parent.image is not None:
                    percent = float(value)
                    if not 0.0 <= percent <= 100.0:
                        raise ValueError(f"{self.SETTING_LABELS.get(name, name)} 必须在 0–100% 之间。")
                    pixel_value = _layout_percent_to_pixels(
                        self.parent.image, name, percent
                    )
                    setattr(self.parent.settings, name, int(pixel_value))
                else:
                    setattr(self.parent.settings, name, self._casts[name](value))
            elif name == "detection_method":
                self.parent.settings.detection_method = DETECTION_VALUES[str(value)]
            elif name == "ocr_engine":
                self.parent.settings.ocr_engine = OCR_ENGINE_VALUES[str(value)]
            elif name == "paddle_lens_mode":
                self.parent.settings.paddle_lens_mode = LENS_MODE_VALUES[str(value)]
            elif name == "headword_sort_mode":
                self.parent.settings.headword_sort_mode = self._sort_label_to_value.get(str(value), "auto")
            elif name == "headword_custom_order":
                self.parent.settings.headword_custom_order = str(value).strip()
            elif name == "headword_custom_fold_accents":
                self.parent.settings.headword_custom_fold_accents = bool(value)
            else:
                setattr(self.parent.settings, name, bool(value))
        if self.parent.image is not None and not str(
            getattr(self.parent.settings, "layout_writing_mode", "horizontal-tb") or "horizontal-tb"
        ).startswith("vertical"):
            if (
                "start_y" in self.vars
                and str(getattr(self.parent.settings, "profile_header_mode", "auto") or "auto")
                == "present"
            ):
                source_y = int(self.parent.settings.start_y)
                source_y = max(0, min(self.parent.image.height, source_y))
                percent = source_y * 100.0 / max(1, self.parent.image.height)
                if percent > 35.0:
                    raise ValueError("页眉不能超过原图高度的 35%。")
                self.parent.settings.profile_header_percent = round(percent, 6)
            if (
                "bottom_y" in self.vars
                and str(getattr(self.parent.settings, "profile_footer_mode", "auto") or "auto")
                == "present"
            ):
                source_y = int(self.parent.settings.bottom_y)
                source_y = max(0, min(self.parent.image.height, source_y))
                percent = (
                    (self.parent.image.height - source_y)
                    * 100.0
                    / max(1, self.parent.image.height)
                )
                if not 0.0 <= percent <= 35.0:
                    raise ValueError("页尾必须位于原图底部 35% 范围内。")
                self.parent.settings.profile_footer_percent = round(percent, 6)

        current_language = str(getattr(self.parent.settings, "ocr_language", "") or "")
        if current_language != previous_language:
            derived = language_effective_settings(
                current_language, self.parent.settings.layout_writing_mode,
            )
            for name, value in derived.items():
                if not hasattr(self.parent.settings, name):
                    continue
                # Keep overrides, replacing only old language defaults.
                if name not in previous_backend or getattr(self.parent.settings, name) == previous_backend[name]:
                    setattr(self.parent.settings, name, value)
        self.parent.settings.paddle_lens_language = str(
            getattr(self.parent.settings, "ocr_language", "") or ""
        )
        self.parent.settings.main_entry_font_family = normalize_content_font_setting(
            self.parent.settings.main_entry_font_family
        )
        self.parent.settings.illustration_label_font_family = normalize_content_font_setting(
            self.parent.settings.illustration_label_font_family
        )
        self.parent.settings.ref_box_font_family = normalize_content_font_setting(
            self.parent.settings.ref_box_font_family
        )
        self.parent.settings.main_entry_font_size = max(5, int(self.parent.settings.main_entry_font_size))
        self.parent.settings.main_entry_width_chars = max(4, int(self.parent.settings.main_entry_width_chars))
        self.parent.settings.main_entry_x_ratio = min(1.25, max(0.0, float(self.parent.settings.main_entry_x_ratio)))
        self.parent.settings.review_entry_font_family = normalize_content_font_setting(
            self.parent.settings.review_entry_font_family
        )
        self.parent.settings.review_simplified_font_family = normalize_content_font_setting(
            self.parent.settings.review_simplified_font_family
        )
        self.parent.settings.review_entry_font_size = max(6, int(self.parent.settings.review_entry_font_size))
        self.parent.settings.review_entry_vertical_padding = min(30, max(0, int(self.parent.settings.review_entry_vertical_padding)))
        self.parent.settings.review_single_cjk_line_height = min(500, max(0, int(self.parent.settings.review_single_cjk_line_height)))
        review_zoom_percent = float(self.parent.settings.review_zoom_percent)
        self.parent.settings.review_zoom_percent = (
            0.0 if review_zoom_percent <= 0 else min(250.0, max(20.0, review_zoom_percent))
        )
        if not 0 <= int(self.parent.settings.crop_parallel_workers) <= 8:
            raise ValueError("切图并行进程数必须为 0–8；0 表示自动，1 表示串行。")
        if not 1.0 <= float(self.parent.settings.paddle_band_width_ratio) <= 100.0:
            raise ValueError("候选带宽比例必须在 1–100 之间；100 即原候选带宽。")
        if int(self.parent.settings.paddle_max_input_side) < 256:
            raise ValueError("OCR输入最大长边必须至少为 256 px。")
        if str(self.parent.settings.paddle_preprocessing) not in {
            "original", "grayscale", "auto_contrast", "binary",
        }:
            raise ValueError("OCR图像预处理必须为 original/grayscale/auto_contrast/binary 之一。")
        if not 10.0 <= float(self.parent.settings.paddle_separator_roi_width_ratio) <= 100.0:
            raise ValueError("Y精修横向分析范围必须在 10–100% 之间。")
        if not 1 <= float(self.parent.settings.right_ratio) <= 100:
            raise ValueError("向右比例必须在 1–100% 之间。")
        if self.parent.settings.headword_sort_mode == "custom":
            parse_custom_order(self.parent.settings.headword_custom_order)
        self._save_integrated_crop_settings()
        self.parent.settings.dictionary_profile_id = self._current_profile_key()
        rules_text = self.rules_text.get("1.0", "end-1c")
        parse_headword_filter_rules(rules_text, "规则编辑框")
        if self.parent.project:
            self.parent.settings.to_json(settings_path(self.parent.project.root))
            write_project_profile(
                project_profile_path(self.parent.project.root),
                self.parent.settings,
                self.parent.settings.dictionary_profile_id,
                force=bool(getattr(self, "_profile_selection_changed", False)),
            )
            rules_path = headword_filter_rules_path(self.parent.project.root, HEADWORD_FILTER_RULES_FILENAME)
            rules_path.parent.mkdir(parents=True, exist_ok=True)
            rules_path.write_text(rules_text.rstrip() + "\n", encoding="utf-8")
            self.parent._request_wordslist_reload(persist=False, redraw=False)
        self.parent.sync_quick_settings(); self.parent.redraw()
        if close:
            self.destroy()
        return True
    except Exception as exc:
        self._last_settings_error = str(exc)
        if show_errors:
            messagebox.showerror("参数无效", str(exc), parent=self)
        return False


# Actual SettingsDialog value initialization (percent/pixel and language choices).

def _setting_var(self, name: str, *, deps: dict[str, Any]) -> tk.Variable:
    tk = deps["tk"]
    _format_layout_percent = deps["_format_layout_percent"]
    _column_pixels_to_percent = deps["_column_pixels_to_percent"]
    LAYOUT_PERCENT_AXES = deps["LAYOUT_PERCENT_AXES"]
    _layout_pixels_to_percent = deps["_layout_pixels_to_percent"]
    if name in self.vars:
        return self.vars[name]
    raw = getattr(self.parent.settings, name)
    choices = self.SETTING_CHOICES.get(name)
    if choices:
        reverse = {value: label for label, value in choices.items()}
        value = reverse.get(str(raw), str(raw))
    elif name == "paddle_left_tolerance":
        value = _format_layout_percent(
            _column_pixels_to_percent(self.parent.settings, raw)
        )
    elif name in LAYOUT_PERCENT_AXES and self.parent.image is not None:
        source_value = (
            self.parent._quick_geometry_value(name)
            if hasattr(self.parent, "_quick_geometry_value")
            else raw
        )
        value = _format_layout_percent(
            _layout_pixels_to_percent(self.parent.image, name, source_value)
        )
    else:
        value = str(raw)
    var = tk.StringVar(value=value)
    self.vars[name] = var
    return var
