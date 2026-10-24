"""Reading/headword/profile revision state changes and preset defaults."""
from __future__ import annotations


def mark_validation_stale(self) -> None:
    """A saved validation result is meaningful only for the exact current settings."""
    if getattr(self.working, "profile_last_validated_pages", None):
        self.working.profile_last_validated_pages = []
    if hasattr(self, "validation_status_var") and not self._validation_running:
        self.validation_status_var.set("设置已修改，需要重新测试")
    if hasattr(self, "feedback_too_many_button"):
        for button in (
            self.feedback_too_many_button,
            self.feedback_good_button,
            self.feedback_too_few_button,
        ):
            button.configure(state="disabled")



def profile_input_changed(self, *, refresh_preview: bool = True) -> None:
    self._profile_revision += 1
    self._mark_validation_stale()
    self._refresh_summary()
    self._refresh_column_adjust_status()
    if refresh_preview and hasattr(self, "template_preview_frame"):
        self.after_idle(self._refresh_template_preview)



def reading_changed(self) -> None:
    self._profile_revision += 1
    self._mark_validation_stale()
    if hasattr(self, "analysis_suggestion_var") and self._analysis_suggestion:
        self._analysis_suggestion = {}
        self.analysis_suggestion_var.set("阅读方向已改变，请重新分析代表页。")
        self.apply_analysis_button.configure(state="disabled")
    self._refresh_language_summary()
    self._refresh_summary()



def set_structure_defaults_for_profile(self, key: str, *, deps) -> None:
    recommended_headword_structures = deps["recommended_headword_structures"]
    defaults = recommended_headword_structures(key)
    self.ordinary_left_edge_var.set(defaults["ordinary_left_edge"])
    self.cjk_allow_bracketed_var.set(defaults["cjk_bracketed"])
    self.cjk_allow_single_var.set(defaults["cjk_single_visual"])
    self.marker_prefix_var.set(defaults["marker_prefix"])
    self.numbered_prefix_var.set(defaults["numbered_prefix"])



def set_tail_defaults_for_profile(self, key: str, *, deps) -> None:
    profile_tail_structure_defaults = deps["profile_tail_structure_defaults"]
    defaults = profile_tail_structure_defaults(key)
    self.tail_allow_pos_var.set(bool(defaults["allow_pos"]))
    self.tail_allow_inflection_var.set(bool(defaults["allow_inflection"]))
    self.tail_allow_variant_var.set(bool(defaults["allow_variant"]))
    self.tail_allow_pronunciation_var.set(bool(defaults["allow_pronunciation"]))
    self.tail_allow_descriptor_var.set(bool(defaults["allow_descriptor"]))
    self.tail_require_selected_var.set(bool(defaults["require_selected"]))
    self.tail_allow_visual_rescue_var.set(bool(defaults["allow_visual_rescue"]))



def set_symbol_defaults_for_profile(self, key: str, *, deps) -> None:
    profile_symbol_inventory_defaults = deps["profile_symbol_inventory_defaults"]
    defaults = profile_symbol_inventory_defaults(key)
    self.symbol_inventory_enabled_var.set(bool(defaults["enabled"]))
    self.entry_marker_symbols_var.set(" ".join(defaults["entry_markers"]))
    self.bracket_open_symbols_var.set(" ".join(defaults["bracket_openers"]))
    self.symbol_visual_rescue_var.set(bool(defaults["visual_rescue"]))
    self.symbol_lane_required_var.set(bool(defaults["lane_required"]))
    self.symbol_lane_tolerance_var.set(int(defaults["lane_tolerance_percent"]))



def specificity_defaults_for_profile(self, key: str, *, deps) -> tuple[int, float, float, float]:
    replace = deps["replace"]
    _ocr_language_code = deps["_ocr_language_code"]
    apply_headword_profile = deps["apply_headword_profile"]
    language_effective_settings = deps["language_effective_settings"]
    temp = replace(self.working)
    temp.ocr_language = _ocr_language_code(self.ocr_language_var.get())
    apply_headword_profile(temp, key)
    for name, value in language_effective_settings(
        temp.ocr_language, temp.layout_writing_mode
    ).items():
        if hasattr(temp, name):
            setattr(temp, name, value)
    column_width = max(1, int(getattr(temp, "column_width", 700) or 700))
    left_percent = (
        float(getattr(temp, "paddle_left_tolerance", 34) or 34)
        * 100.0 / column_width
    )
    return (
        left_percent,
        float(getattr(temp, "paddle_height_ratio", 1.08)),
        float(getattr(temp, "paddle_boldness_ratio", 1.12)),
        float(getattr(temp, "paddle_min_candidate_score", 1.0)),
    )



def reset_specificity_for_profile(self, key: str) -> None:
    left, height, bold, score = self._specificity_defaults_for_profile(key)
    self.headword_left_tolerance_var.set(left)
    self.headword_height_ratio_var.set(round(height, 2))
    self.headword_boldness_ratio_var.set(round(bold, 2))
    self.headword_min_score_var.set(round(score, 2))



def headword_changed(self, *, deps) -> None:
    _normalize_cjk_visual_symbol_roles = deps["_normalize_cjk_visual_symbol_roles"]
    # Selecting a structure preset seeds human-readable parser checkboxes;
    # users may then customize them without opening advanced parameters.
    self.headword_tuning_level_var.set(0)
    key = self._current_profile_key()
    self._set_structure_defaults_for_profile(key)
    self._set_tail_defaults_for_profile(key)
    self._set_symbol_defaults_for_profile(key)
    if key == "cjk_visual":
        (
            normalized_entry,
            normalized_bracket,
            normalized_samples,
        ) = _normalize_cjk_visual_symbol_roles(
            self.entry_marker_symbols_var.get(),
            self.bracket_open_symbols_var.get(),
            list(getattr(self, "visual_marker_samples", []) or []),
        )
        self.entry_marker_symbols_var.set(normalized_entry)
        self.bracket_open_symbols_var.set(normalized_bracket)
        self.visual_marker_samples = normalized_samples
        self._refresh_symbol_template_summary()
    self._reset_specificity_for_profile(key)
    self._profile_revision += 1
    self._mark_validation_stale()
    self._refresh_headword_description()
    self._refresh_summary()



def headword_structure_changed(self) -> None:
    self._profile_revision += 1
    self._mark_validation_stale()
    self._refresh_headword_structure_summary()
    self._refresh_headword_specificity_visibility()
    self._refresh_summary()



def headword_specificity_changed(self) -> None:
    self._profile_revision += 1
    self._mark_validation_stale()
    self._refresh_headword_tuning_status()
    self._refresh_symbol_template_summary()
    self._refresh_summary()



def refresh_headword_tuning_status(self) -> None:
    if not hasattr(self, "headword_tuning_status_var"):
        return
    level = max(-2, min(2, int(self.headword_tuning_level_var.get())))
    labels = {
        -2: "当前自动调节：明显放宽（-2）",
        -1: "当前自动调节：轻度放宽（-1）",
        0: "当前自动调节：标准（0）",
        1: "当前自动调节：轻度收紧（+1）",
        2: "当前自动调节：明显收紧（+2）",
    }
    self.headword_tuning_status_var.set(labels[level])



def custom_name_changed(self, *, deps) -> None:
    ordered_headword_profiles = deps["ordered_headword_profiles"]
    # Renaming the custom structure is presentation metadata; recognition
    # settings are unchanged, so a completed Profile test remains valid.
    current = self._current_profile_key()
    self.profile_choices = ordered_headword_profiles(self.custom_name_var.get())
    self.profile_label_to_key = dict(self.profile_choices)
    self.headword_combo.configure(values=tuple(label for label, _key in self.profile_choices))
    self.headword_profile_var.set(self._profile_label_for_key(current))
    self._refresh_headword_description()
    self._refresh_summary()



def ocr_language_changed(self, *, deps) -> None:
    _ocr_language_code = deps["_ocr_language_code"]
    OCR_TO_INDEX_LANGUAGE = deps["OCR_TO_INDEX_LANGUAGE"]
    language = _ocr_language_code(self.ocr_language_var.get())
    auto_index = OCR_TO_INDEX_LANGUAGE.get(language)
    if auto_index:
        self.index_language_var.set(auto_index)
    self._refresh_language_summary()
    self._refresh_summary()



def profile_label_for_key(self, key: str, *, deps) -> str:
    dictionary_profile_preset = deps["dictionary_profile_preset"]
    for label, value in self.profile_choices:
        if value == key:
            return label
    try:
        wanted = dictionary_profile_preset(key).display_name
    except Exception:
        wanted = ""
    for label, value in self.profile_choices:
        try:
            if dictionary_profile_preset(value).display_name == wanted:
                return label
        except Exception:
            continue
    return self.profile_choices[0][0] if self.profile_choices else ""
