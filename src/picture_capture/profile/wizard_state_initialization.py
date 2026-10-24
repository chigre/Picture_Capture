"""Profile Wizard working-variable initialization; no Tk root creation.

The original wizard method passes all live globals on each call.
"""
from __future__ import annotations


def build_vars(self, *, deps) -> None:
    tk = deps["tk"]
    reading_choice_from_settings = deps["reading_choice_from_settings"]
    _label_for_value = deps["_label_for_value"]
    SEPARATOR_LABEL_TO_VALUE = deps["SEPARATOR_LABEL_TO_VALUE"]
    HEADER_LABEL_TO_VALUE = deps["HEADER_LABEL_TO_VALUE"]
    FOOTER_LABEL_TO_VALUE = deps["FOOTER_LABEL_TO_VALUE"]
    SIDE_LABEL_TO_VALUE = deps["SIDE_LABEL_TO_VALUE"]
    OCR_LANGUAGE_LABEL_TO_VALUE = deps["OCR_LANGUAGE_LABEL_TO_VALUE"]
    OCR_TO_INDEX_LANGUAGE = deps["OCR_TO_INDEX_LANGUAGE"]
    _ocr_language_code = deps["_ocr_language_code"]
    VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE = deps["VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE"]
    VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE = deps["VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE"]
    parse_visual_marker_samples = deps["parse_visual_marker_samples"]
    profile_symbol_inventory_defaults = deps["profile_symbol_inventory_defaults"]
    profile_tail_structure_defaults = deps["profile_tail_structure_defaults"]
    ordered_headword_profiles = deps["ordered_headword_profiles"]
    s = self.working
    self.dictionary_full_name_var = tk.StringVar(value=str(s.dictionary_full_name or ""))
    self.dictionary_abbreviation_var = tk.StringVar(value=str(s.dictionary_abbreviation or ""))
    self.dictionary_isbn_var = tk.StringVar(value=str(s.dictionary_isbn or ""))
    self.dictionary_body_page_range_var = tk.StringVar(value=str(s.dictionary_body_page_range or ""))
    self.reading_var = tk.StringVar(value=reading_choice_from_settings(s))
    self.columns_var = tk.IntVar(value=max(1, int(s.columns)))
    self.selected_column_index = 0
    self.column_adjust_status_var = tk.StringVar(value="")
    self.separator_var = tk.StringVar(value=_label_for_value(
        SEPARATOR_LABEL_TO_VALUE, str(s.layout_column_separator_mode or "auto"), "自动判断",
    ))
    self.header_mode_var = tk.StringVar(value=_label_for_value(
        HEADER_LABEL_TO_VALUE,
        str(getattr(s, "profile_header_mode", "auto") or "auto"),
        "自动检测页眉",
    ))
    footer_value = str(getattr(s, "profile_footer_mode", "auto") or "auto")
    self.footer_mode_var = tk.StringVar(value=_label_for_value(
        FOOTER_LABEL_TO_VALUE, footer_value, "自动检测页尾",
    ))
    self.side_mode_var = tk.StringVar(value=_label_for_value(
        SIDE_LABEL_TO_VALUE,
        str(getattr(s, "profile_side_content_mode", "none") or "none"),
        "无页边占位内容",
    ))
    self.first_variant_var = tk.StringVar(value=str(getattr(s, "profile_first_page_variant", "A") or "A"))
    self.header_percent_var = tk.DoubleVar(value=float(getattr(s, "profile_header_percent", 6.0)))
    self.footer_percent_var = tk.DoubleVar(value=float(getattr(s, "profile_footer_percent", 5.0)))
    self.side_percent_var = tk.DoubleVar(value=float(getattr(s, "profile_side_percent", 8.0)))
    self.side_percent_a_var = tk.DoubleVar(value=float(
        getattr(s, "profile_side_percent_a", getattr(s, "profile_side_percent", 8.0))
    ))
    self.side_percent_b_var = tk.DoubleVar(value=float(
        getattr(s, "profile_side_percent_b", getattr(s, "profile_side_percent", 8.0))
    ))
    self.ocr_language_var = tk.StringVar(value=_label_for_value(
        OCR_LANGUAGE_LABEL_TO_VALUE, str(s.ocr_language or "eng"), str(s.ocr_language or "eng"),
    ))
    initial_index = str(s.dictionary_index_language or "").strip()
    if not initial_index:
        initial_index = OCR_TO_INDEX_LANGUAGE.get(_ocr_language_code(self.ocr_language_var.get()), "")
    self.index_language_var = tk.StringVar(value=initial_index)
    self.content_language_var = tk.StringVar(value=str(s.dictionary_content_language or ""))
    self.custom_name_var = tk.StringVar(value=str(getattr(s, "dictionary_custom_profile_name", "") or ""))
    self.headword_tuning_level_var = tk.IntVar(
        value=max(-2, min(2, int(getattr(s, "profile_headword_tuning_level", 0) or 0)))
    )
    column_width_px = max(1, int(getattr(s, "column_width", 700) or 700))
    left_tolerance_percent = (
        float(getattr(s, "paddle_left_tolerance", 34) or 34)
        * 100.0 / column_width_px
    )
    self.headword_left_tolerance_var = tk.DoubleVar(
        value=max(0.0, min(100.0, round(left_tolerance_percent, 2)))
    )
    self.headword_height_ratio_var = tk.DoubleVar(
        value=max(0.5, float(getattr(s, "paddle_height_ratio", 1.08) or 1.08))
    )
    self.headword_boldness_ratio_var = tk.DoubleVar(
        value=max(0.5, float(getattr(s, "paddle_boldness_ratio", 1.12) or 1.12))
    )
    self.headword_min_score_var = tk.DoubleVar(
        value=max(0.0, float(getattr(s, "paddle_min_candidate_score", 1.0) or 1.0))
    )

    self.profile_choices = ordered_headword_profiles(self.custom_name_var.get())
    self.profile_label_to_key = dict(self.profile_choices)
    self.headword_profile_var = tk.StringVar(value=self._profile_label_for_key(s.dictionary_profile_id))
    structure_defaults = recommended_headword_structures(s.dictionary_profile_id)
    parser_controls_saved = int(
        getattr(s, "profile_parser_controls_version", 0) or 0
    ) >= 1
    self.ordinary_left_edge_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_allow_ordinary_left_edge", True))
        if parser_controls_saved else structure_defaults["ordinary_left_edge"]
    ))
    self.numbered_prefix_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_allow_numbered_prefix", False))
        if parser_controls_saved else structure_defaults["numbered_prefix"]
    ))
    self.marker_prefix_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_allow_marker_prefix", False))
        if parser_controls_saved else structure_defaults["marker_prefix"]
    ))
    script_guard_saved = int(
        getattr(s, "profile_headword_script_guard_version", 0) or 0
    ) >= 1
    self.headword_script_guard_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_headword_script_guard_enabled", True))
        if script_guard_saved else True
    ))
    tail_defaults = profile_tail_structure_defaults(s.dictionary_profile_id)
    tail_controls_saved = int(
        getattr(s, "profile_tail_structure_version", 0) or 0
    ) >= 1
    self.tail_allow_pos_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_tail_allow_pos", True))
        if tail_controls_saved else tail_defaults["allow_pos"]
    ))
    self.tail_allow_inflection_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_tail_allow_inflection", True))
        if tail_controls_saved else tail_defaults["allow_inflection"]
    ))
    self.tail_allow_variant_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_tail_allow_variant", True))
        if tail_controls_saved else tail_defaults["allow_variant"]
    ))
    self.tail_allow_pronunciation_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_tail_allow_pronunciation", False))
        if tail_controls_saved else tail_defaults["allow_pronunciation"]
    ))
    self.tail_allow_descriptor_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_tail_allow_descriptor", True))
        if tail_controls_saved else tail_defaults["allow_descriptor"]
    ))
    self.tail_require_selected_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_tail_require_selected", True))
        if tail_controls_saved else tail_defaults["require_selected"]
    ))
    self.tail_allow_visual_rescue_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_tail_allow_visual_rescue", False))
        if tail_controls_saved else tail_defaults["allow_visual_rescue"]
    ))
    self.tail_structure_summary_var = tk.StringVar(value="")
    symbol_defaults = profile_symbol_inventory_defaults(s.dictionary_profile_id)
    symbol_inventory_saved = int(
        getattr(s, "profile_symbol_inventory_version", 0) or 0
    ) >= 1
    self.symbol_inventory_enabled_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_symbol_inventory_enabled", True))
        if symbol_inventory_saved else bool(symbol_defaults["enabled"])
    ))
    self.entry_marker_symbols_var = tk.StringVar(value=(
        str(getattr(s, "profile_entry_marker_symbols", "") or "")
        if symbol_inventory_saved
        else " ".join(symbol_defaults["entry_markers"])
    ))
    self.bracket_open_symbols_var = tk.StringVar(value=(
        str(getattr(s, "profile_bracket_open_symbols", "") or "")
        if symbol_inventory_saved
        else " ".join(symbol_defaults["bracket_openers"])
    ))
    self.symbol_visual_rescue_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_symbol_visual_rescue_enabled", True))
        if symbol_inventory_saved else bool(symbol_defaults["visual_rescue"])
    ))
    self.symbol_lane_required_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_symbol_lane_required", True))
        if symbol_inventory_saved else bool(symbol_defaults["lane_required"])
    ))
    self.symbol_lane_tolerance_var = tk.IntVar(value=(
        max(
            20,
            min(
                120,
                int(getattr(s, "profile_symbol_lane_tolerance_percent", 50) or 50),
            ),
        )
        if symbol_inventory_saved
        else int(symbol_defaults["lane_tolerance_percent"])
    ))
    template_mode = str(
        getattr(s, "profile_symbol_template_mode", "combined") or "combined"
    )
    self.symbol_template_mode_var = tk.StringVar(value=_label_for_value(
        VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE,
        template_mode,
        "字符符号集 + 视觉样本",
    ))
    template_group_mode = str(
        getattr(s, "profile_symbol_template_group_mode", "role") or "role"
    )
    self.symbol_template_group_var = tk.StringVar(value=_label_for_value(
        VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE,
        template_group_mode,
        "按角色合并（推荐）",
    ))
    self.symbol_template_threshold_var = tk.DoubleVar(value=max(
        0.35,
        min(
            0.95,
            float(getattr(s, "profile_symbol_template_threshold", 0.68) or 0.68),
        ),
    ))
    self.symbol_template_debug_var = tk.BooleanVar(
        value=bool(getattr(s, "profile_symbol_template_debug_enabled", False))
    )
    self.visual_marker_samples = parse_visual_marker_samples(
        getattr(s, "profile_symbol_templates_json", "")
    )
    self.effective_entry_markers_var = tk.StringVar(value="")
    self.effective_bracket_markers_var = tk.StringVar(value="")
    self.visual_marker_sample_count_var = tk.StringVar(value="")
    self.cjk_allow_single_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_cjk_allow_single_headword", True))
        if parser_controls_saved else structure_defaults["cjk_single_visual"]
    ))
    self.cjk_allow_bracketed_var = tk.BooleanVar(value=(
        bool(getattr(s, "profile_cjk_allow_bracketed_headword", True))
        if parser_controls_saved else structure_defaults["cjk_bracketed"]
    ))
    self.cjk_require_left_edge_var = tk.BooleanVar(
        value=bool(getattr(s, "profile_cjk_require_left_edge", True))
    )
    self.cjk_brackets_in_body_var = tk.BooleanVar(
        value=bool(getattr(s, "profile_cjk_brackets_in_body", False))
    )
    self.cjk_require_visual_var = tk.BooleanVar(
        value=bool(getattr(s, "profile_cjk_require_visual_evidence", False))
    )
    self.cjk_right_context_enabled_var = tk.BooleanVar(
        value=bool(getattr(s, "profile_cjk_right_context_enabled", True))
    )
    self.cjk_right_context_width_var = tk.IntVar(
        value=max(
            30,
            min(
                200,
                int(getattr(s, "profile_cjk_right_context_width_percent", 80) or 80),
            ),
        )
    )

    detection_vars = (
        self.reading_var, self.columns_var, self.separator_var,
        self.header_mode_var, self.footer_mode_var, self.side_mode_var,
        self.first_variant_var, self.header_percent_var,
        self.footer_percent_var, self.side_percent_var,
        self.side_percent_a_var, self.side_percent_b_var,
        self.ocr_language_var,
    )
    for var in detection_vars:
        var.trace_add("write", lambda *_args: self.after_idle(self._profile_input_changed))
    # Project metadata changes the summary only; it does not invalidate a
    # successful recognition test.
    for var in (
        self.dictionary_full_name_var, self.dictionary_abbreviation_var,
        self.dictionary_isbn_var, self.index_language_var, self.content_language_var,
    ):
        var.trace_add("write", lambda *_args: self.after_idle(self._refresh_summary))

    for var in (
        self.headword_left_tolerance_var,
        self.headword_height_ratio_var,
        self.headword_boldness_ratio_var,
        self.headword_min_score_var,
        self.cjk_right_context_width_var,
        self.entry_marker_symbols_var,
        self.bracket_open_symbols_var,
        self.symbol_lane_tolerance_var,
        self.symbol_template_mode_var,
        self.symbol_template_group_var,
        self.symbol_template_threshold_var,
    ):
        var.trace_add(
            "write", lambda *_args: self.after_idle(self._headword_specificity_changed)
        )
    for var in (self.entry_marker_symbols_var, self.bracket_open_symbols_var):
        var.trace_add(
            "write", lambda *_args: self.after_idle(self._refresh_symbol_template_summary)
        )
    self._refresh_symbol_template_summary()

