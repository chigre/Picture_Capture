"""Owner for Project Profile settings assembly from visible wizard controls."""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..models import AppSettings


def settings_from_ui(self, *, deps) -> AppSettings:
    replace = deps["replace"]
    apply_reading_choice = deps["apply_reading_choice"]
    SEPARATOR_LABEL_TO_VALUE = deps["SEPARATOR_LABEL_TO_VALUE"]
    HEADER_LABEL_TO_VALUE = deps["HEADER_LABEL_TO_VALUE"]
    FOOTER_LABEL_TO_VALUE = deps["FOOTER_LABEL_TO_VALUE"]
    SIDE_LABEL_TO_VALUE = deps["SIDE_LABEL_TO_VALUE"]
    _ocr_language_code = deps["_ocr_language_code"]
    split_configured_symbols = deps["split_configured_symbols"]
    _normalize_cjk_visual_symbol_roles = deps["_normalize_cjk_visual_symbol_roles"]
    VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE = deps["VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE"]
    VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE = deps["VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE"]
    serialize_visual_marker_samples = deps["serialize_visual_marker_samples"]
    apply_headword_profile = deps["apply_headword_profile"]
    language_effective_settings = deps["language_effective_settings"]
    apply_headword_tuning = deps["apply_headword_tuning"]
    PROFILE_SETUP_VERSION = deps["PROFILE_SETUP_VERSION"]
    s = replace(self.working)
    s.dictionary_full_name = self.dictionary_full_name_var.get().strip()
    s.dictionary_abbreviation = self.dictionary_abbreviation_var.get().strip()
    s.dictionary_isbn = self.dictionary_isbn_var.get().strip()
    s.dictionary_body_page_range = self.dictionary_body_page_range_var.get().strip()
    apply_reading_choice(s, self.reading_var.get())
    # Runtime geometry uses the project-confirmed column count. Automatic
    # analysis above is a setup aid, not a hidden per-page detector.
    s.layout_columns_policy = "fixed"
    s.columns = max(1, int(self.columns_var.get()))
    s.column_start_offsets = self._column_offsets_for_count(s.columns)
    s.layout_column_separator_mode = SEPARATOR_LABEL_TO_VALUE.get(
        self.separator_var.get(), "auto"
    )
    s.profile_header_mode = HEADER_LABEL_TO_VALUE.get(
        self.header_mode_var.get(), "auto"
    )
    s.profile_footer_mode = FOOTER_LABEL_TO_VALUE.get(
        self.footer_mode_var.get(), "auto"
    )
    s.profile_side_content_mode = SIDE_LABEL_TO_VALUE.get(
        self.side_mode_var.get(), "none"
    )
    s.profile_page_pair_mode = (
        "alternate" if s.profile_side_content_mode in {"outer", "inner"} else "same"
    )
    s.profile_first_page_variant = self.first_variant_var.get()
    s.profile_header_percent = max(0.0, min(35.0, float(self.header_percent_var.get())))
    s.profile_footer_percent = max(0.0, min(35.0, float(self.footer_percent_var.get())))
    s.profile_side_percent = max(0.0, min(30.0, float(self.side_percent_var.get())))
    s.profile_side_percent_a = max(
        0.0, min(30.0, float(self.side_percent_a_var.get()))
    )
    s.profile_side_percent_b = max(
        0.0, min(30.0, float(self.side_percent_b_var.get()))
    )
    s.dictionary_custom_profile_name = self.custom_name_var.get().strip()
    s.ocr_language = _ocr_language_code(self.ocr_language_var.get())
    s.dictionary_index_language = self.index_language_var.get().strip()
    s.dictionary_content_language = self.content_language_var.get().strip()
    s.profile_headword_tuning_level = max(
        -2, min(2, int(self.headword_tuning_level_var.get()))
    )
    s.profile_parser_controls_version = 1
    s.profile_allow_ordinary_left_edge = bool(self.ordinary_left_edge_var.get())
    s.profile_allow_numbered_prefix = bool(self.numbered_prefix_var.get())
    s.profile_allow_marker_prefix = bool(self.marker_prefix_var.get())
    s.profile_headword_script_guard_version = 1
    s.profile_headword_script_guard_enabled = bool(
        self.headword_script_guard_var.get()
    )
    s.profile_tail_structure_version = 1
    s.profile_tail_allow_pos = bool(self.tail_allow_pos_var.get())
    s.profile_tail_allow_inflection = bool(self.tail_allow_inflection_var.get())
    s.profile_tail_allow_variant = bool(self.tail_allow_variant_var.get())
    s.profile_tail_allow_pronunciation = bool(
        self.tail_allow_pronunciation_var.get()
    )
    s.profile_tail_allow_descriptor = bool(self.tail_allow_descriptor_var.get())
    s.profile_tail_require_selected = bool(self.tail_require_selected_var.get())
    s.profile_tail_allow_visual_rescue = bool(
        self.tail_allow_visual_rescue_var.get()
    )
    profile_key = self._current_profile_key()
    s.profile_symbol_inventory_version = 1
    s.profile_symbol_inventory_enabled = bool(
        self.symbol_inventory_enabled_var.get()
    )
    entry_symbols = " ".join(
        split_configured_symbols(self.entry_marker_symbols_var.get())
    )
    bracket_symbols = " ".join(
        split_configured_symbols(self.bracket_open_symbols_var.get())
    )
    visual_samples = [
        dict(item)
        for item in getattr(self, "visual_marker_samples", []) or []
    ]
    if profile_key == "cjk_visual":
        entry_symbols, bracket_symbols, visual_samples = (
            _normalize_cjk_visual_symbol_roles(
                entry_symbols,
                bracket_symbols,
                visual_samples,
            )
        )
        # A CJK bracket opener never becomes an independent prefix merely
        # because the old buggy Profile once stored it in both roles.
        if not entry_symbols:
            s.profile_allow_marker_prefix = False
    s.profile_entry_marker_symbols = entry_symbols
    s.profile_bracket_open_symbols = bracket_symbols
    s.profile_symbol_visual_rescue_enabled = bool(
        self.symbol_visual_rescue_var.get()
    )
    s.profile_symbol_lane_required = bool(
        self.symbol_lane_required_var.get()
    )
    s.profile_symbol_lane_tolerance_percent = max(
        20, min(120, int(self.symbol_lane_tolerance_var.get()))
    )
    s.profile_symbol_template_version = 1
    s.profile_symbol_template_mode = VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE.get(
        self.symbol_template_mode_var.get(), "combined"
    )
    s.profile_symbol_template_group_mode = (
        VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE.get(
            self.symbol_template_group_var.get(), "role"
        )
    )
    s.profile_symbol_template_threshold = max(
        0.35, min(0.95, float(self.symbol_template_threshold_var.get()))
    )
    s.profile_symbol_templates_json = serialize_visual_marker_samples(
        visual_samples
    )
    s.profile_symbol_template_debug_enabled = bool(
        self.symbol_template_debug_var.get()
    )
    s.profile_cjk_allow_single_headword = bool(self.cjk_allow_single_var.get())
    s.profile_cjk_allow_bracketed_headword = bool(self.cjk_allow_bracketed_var.get())
    s.profile_cjk_require_left_edge = bool(self.cjk_require_left_edge_var.get())
    s.profile_cjk_brackets_in_body = bool(self.cjk_brackets_in_body_var.get())
    s.profile_cjk_require_visual_evidence = bool(self.cjk_require_visual_var.get())
    s.profile_cjk_right_context_enabled = bool(
        self.cjk_right_context_enabled_var.get()
    )
    s.profile_cjk_right_context_width_percent = max(
        30, min(200, int(self.cjk_right_context_width_var.get()))
    )
    apply_headword_profile(s, profile_key)
    for name, value in language_effective_settings(s.ocr_language, s.layout_writing_mode).items():
        if hasattr(s, name):
            setattr(s, name, value)
    apply_headword_tuning(s, profile_key, s.profile_headword_tuning_level)
    # The preset may seed the hidden legacy rescue setting, but after Profile
    # step 3 the user's explicit tail-structure choice is authoritative.
    s.paddle_allow_strong_edge_visual_rescue = bool(
        s.profile_tail_allow_visual_rescue
    )
    # Wizard specificity values are explicit project overrides and therefore
    # take precedence over preset/tuning defaults.
    left_percent = max(
        0.0, min(100.0, float(self.headword_left_tolerance_var.get()))
    )
    column_width = max(1, int(getattr(s, "column_width", 1) or 1))
    s.paddle_left_tolerance = max(
        1, int(round(column_width * left_percent / 100.0))
    )
    s.paddle_height_ratio = max(
        0.5, min(3.0, float(self.headword_height_ratio_var.get()))
    )
    s.paddle_boldness_ratio = max(
        0.5, min(3.0, float(self.headword_boldness_ratio_var.get()))
    )
    s.paddle_min_candidate_score = max(
        0.0, min(12.0, float(self.headword_min_score_var.get()))
    )
    s.profile_setup_version = PROFILE_SETUP_VERSION
    return s



def refresh_summary(self, *, deps) -> None:
    profile_summary_tags = deps["profile_summary_tags"]
    try:
        settings = self._settings_from_ui()
        self.summary_var.set("  ｜  ".join(profile_summary_tags(settings)))
    except Exception:
        return
