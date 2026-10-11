"""OCR headword-structure controls shared with the Project Profile wizard.

All fields bind directly to the same AppSettings values and v3 project profile.
The compact popup owns only Tk widgets, never a duplicate parser policy.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ..dictionary_profile import (
    dictionary_profile_preset, profile_symbol_inventory_defaults,
    profile_tail_structure_defaults,
)
from ..profile_semantics import (
    apply_headword_profile, ordered_headword_profiles,
    recommended_headword_structures,
)
from ..profile_setup import _normalize_cjk_visual_symbol_roles
from ..visual_marker_templates import (
    parse_visual_marker_samples, serialize_visual_marker_samples,
    split_configured_symbols,
)
from .compact_profile_persistence import (
    persist_profile_changes, profile_changes_allowed,
)


HEADWORD_CHECKS = (
    ("普通左缘短词", "profile_allow_ordinary_left_edge", "parser"),
    ("【括号词】", "profile_cjk_allow_bracketed_headword", "parser"),
    ("大字单字", "profile_cjk_allow_single_headword", "parser"),
    ("固定符号开头（○●◇◆...；\n不包括【括号】）", "profile_allow_marker_prefix", "parser"),
    ("编号开头（1. 2. ...）", "profile_allow_numbered_prefix", "parser"),
    ("按OCR语言排除不兼容的\n词头首字符（推荐）", "profile_headword_script_guard_enabled", "script"),
)
TAIL_CHECKS = (
    ("词性POS（s.m. / v.tr. agg. / adj. ...）", "profile_tail_allow_pos", "tail"),
    ("词形 / 屈折变化\n（复数、阴阳性、变位提示等）", "profile_tail_allow_inflection", "tail"),
    ("变体 / 性数变化\n（如 , da / , ria 等紧随词头的变体）", "profile_tail_allow_variant", "tail"),
    ("发音 / 音标", "profile_tail_allow_pronunciation", "tail"),
    ("描述型结构\n（前缀、后缀、缩写、sigla/abbreviazione等）", "profile_tail_allow_descriptor", "tail"),
    ("普通左缘词至少需要命中一种\n上面勾选的词后结构", "profile_tail_require_selected", "tail"),
    ("词后结构OCR失败时，允许\n“严格左缘+粗体”视觉补救", "profile_tail_allow_visual_rescue", "tail"),
)
SYMBOL_CHECKS = (
    ("启用独立入口标记符号集\n（○●◇◆...）", "profile_symbol_inventory_enabled", "symbol"),
    ("OCR漏掉/错认符号时允许\n视觉形状补救", "profile_symbol_visual_rescue_enabled", "symbol"),
    ("使用同栏 marker lane\n过滤正文中的相似符号", "profile_symbol_lane_required", "symbol"),
)
CJK_CHECKS = (
    ("必须靠近栏左缘", "profile_cjk_require_left_edge", "cjk"),
    ("只有视觉明显突出时才把\n单字/括号词当词头", "profile_cjk_require_visual_evidence", "cjk"),
    ("分析大字右侧留白\n（仅辅助“大字单字”判断）", "profile_cjk_right_context_enabled", "cjk"),
)

# Field name, label, min, max, integer, unit.
NUMBER_FIELDS = (
    ("profile_symbol_lane_tolerance_percent", "lane 容差", 20, 120, True, "%行高"),
    ("paddle_left_tolerance", "栏左缘容差", 0, 100, False, "%单栏宽"),
    ("paddle_height_ratio", "文字大小倍率≥", 0.5, 3.0, False, ""),
    ("paddle_boldness_ratio", "粗体倍率≥", 0.5, 3.0, False, ""),
    ("paddle_min_candidate_score", "候选强度≥", 0, 12, False, ""),
    ("profile_cjk_right_context_width_percent", "大字右侧检测宽度", 30, 200, True, "%大字高度"),
)
NUMBER_BOUNDS = {
    name: (low, high, integer) for name, _label, low, high, integer, _unit
    in NUMBER_FIELDS
}


def read_profile_numeric(settings: Any, name: str) -> float | int:
    """Profile presents left-edge tolerance in %, OCR stores it in pixels."""
    if name == "paddle_left_tolerance":
        return round(
            100.0 * float(settings.paddle_left_tolerance) /
            max(1, int(settings.column_width)), 2,
        )
    return getattr(settings, name)


def parse_profile_numeric(settings: Any, name: str, raw: str) -> float | int:
    low, high, integer = NUMBER_BOUNDS[name]
    value = int(raw.strip()) if integer else float(raw.strip())
    if not low <= value <= high:
        raise ValueError(f"{name} 超出允许范围 {low:g}–{high:g}")
    if name == "paddle_left_tolerance":
        return max(1, round(int(settings.column_width) * value / 100.0))
    return value


def profile_label_for_current(
    profile_id: str, choices: list[tuple[str, str]],
) -> str:
    """Use the same legacy-preset equivalence as the Profile wizard."""
    for caption, key in choices:
        if key == profile_id:
            return caption
    try:
        wanted = dictionary_profile_preset(profile_id).display_name
    except (KeyError, ValueError):
        wanted = ""
    for caption, key in choices:
        try:
            if dictionary_profile_preset(key).display_name == wanted and wanted:
                return caption
        except (KeyError, ValueError):
            continue
    return choices[0][0] if choices else ""


def build_headword_profile_menu(app: Any, parent: tk.Misc) -> ttk.Frame:
    panel = ttk.Frame(parent, padding=(4, 4, 4, 8))
    bool_vars: dict[str, tk.BooleanVar] = {}
    text_vars: dict[str, tk.StringVar] = {}
    num_vars: dict[str, tk.StringVar] = {}
    profile_choices = ordered_headword_profiles(
        str(getattr(app.settings, "dictionary_custom_profile_name", "")),
    )
    labels = {key: caption for caption, key in profile_choices}
    keys = {caption: key for caption, key in profile_choices}
    preset_var = tk.StringVar()

    def row() -> ttk.Frame:
        frame = ttk.Frame(panel)
        frame.pack(fill="x", pady=(2, 2))
        return frame

    def heading(title: str) -> None:
        ttk.Label(
            row(), text=title, font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")

    def divider() -> None:
        ttk.Separator(panel, orient="horizontal").pack(fill="x", pady=(7, 6))

    def refresh() -> None:
        settings = app.settings
        preset_var.set(profile_label_for_current(
            settings.dictionary_profile_id, profile_choices,
        ))
        for key, var in bool_vars.items():
            var.set(bool(getattr(settings, key)))
        for key, var in text_vars.items():
            var.set(str(getattr(settings, key) or ""))
        for key, var in num_vars.items():
            value = read_profile_numeric(settings, key)
            var.set(f"{value:.2f}".rstrip("0").rstrip(".")
                    if isinstance(value, float) else str(value))

    def persist() -> None:
        persist_profile_changes(app)

    def check_group(name: str, value: bool, group: str) -> None:
        if not profile_changes_allowed(app):
            refresh()
            return
        settings = app.settings
        setattr(settings, name, value)
        if group == "parser":
            settings.profile_parser_controls_version = 1
        elif group == "script":
            settings.profile_headword_script_guard_version = 1
        elif group == "tail":
            settings.profile_tail_structure_version = 1
            if name == "profile_tail_allow_visual_rescue":
                settings.paddle_allow_strong_edge_visual_rescue = value
        elif group == "symbol":
            settings.profile_symbol_inventory_version = 1
        persist()

    def add_check(title: str, name: str, group: str) -> None:
        variable = tk.BooleanVar()
        bool_vars[name] = variable
        ttk.Checkbutton(
            row(), text=title, variable=variable,
            command=lambda n=name, v=variable, g=group:
                check_group(n, bool(v.get()), g),
        ).pack(anchor="w")

    def numeric_save(name: str) -> None:
        try:
            value = parse_profile_numeric(app.settings, name, num_vars[name].get())
        except (ValueError, OverflowError) as exc:
            app.status_var.set(f"{name}：请输入允许范围内的数值（{exc}）")
            refresh()
            return
        if not profile_changes_allowed(app):
            refresh()
            return
        setattr(app.settings, name, value)
        persist()
        refresh()

    def add_number(name: str, caption: str, suffix: str) -> None:
        frame = row()
        ttk.Label(frame, text=caption).pack(side="left", padx=(0, 5))
        variable = tk.StringVar()
        num_vars[name] = variable
        entry = ttk.Entry(frame, textvariable=variable, width=7, justify="center")
        entry.pack(side="left")
        entry.bind("<Return>", lambda _event, key=name: numeric_save(key))
        entry.bind("<FocusOut>", lambda _event, key=name: numeric_save(key))
        if suffix:
            ttk.Label(frame, text=suffix).pack(side="left", padx=(4, 0))

    def save_symbols(name: str) -> None:
        if not profile_changes_allowed(app):
            refresh()
            return
        settings = app.settings
        tokens = " ".join(split_configured_symbols(text_vars[name].get()))
        setattr(settings, name, tokens)
        settings.profile_symbol_inventory_version = 1
        if settings.dictionary_profile_id == "cjk_visual":
            entry, bracket, samples = _normalize_cjk_visual_symbol_roles(
                settings.profile_entry_marker_symbols,
                settings.profile_bracket_open_symbols,
                parse_visual_marker_samples(settings.profile_symbol_templates_json),
            )
            settings.profile_entry_marker_symbols = entry
            settings.profile_bracket_open_symbols = bracket
            settings.profile_symbol_templates_json = serialize_visual_marker_samples(samples)
            if not entry:
                settings.profile_allow_marker_prefix = False
        persist()
        refresh()

    def add_symbols(name: str, label: str) -> None:
        frame = row()
        ttk.Label(frame, text=label).pack(anchor="w")
        variable = tk.StringVar()
        text_vars[name] = variable
        entry = ttk.Entry(frame, textvariable=variable)
        entry.pack(fill="x", expand=True, pady=(2, 0))
        entry.bind("<Return>", lambda _e, n=name: save_symbols(n))
        entry.bind("<FocusOut>", lambda _e, n=name: save_symbols(n))

    def choose_preset(_event: tk.Event | None = None) -> None:
        name = keys.get(preset_var.get())
        if not name or not profile_changes_allowed(app):
            refresh()
            return
        settings = app.settings
        apply_headword_profile(settings, name)
        settings.profile_headword_tuning_level = 0
        defaults = recommended_headword_structures(name)
        for source, field in (
            ("ordinary_left_edge", "profile_allow_ordinary_left_edge"),
            ("cjk_bracketed", "profile_cjk_allow_bracketed_headword"),
            ("cjk_single_visual", "profile_cjk_allow_single_headword"),
            ("marker_prefix", "profile_allow_marker_prefix"),
            ("numbered_prefix", "profile_allow_numbered_prefix"),
        ):
            setattr(settings, field, defaults[source])
        settings.profile_parser_controls_version = 1
        tails = profile_tail_structure_defaults(name)
        for short, field in (
            ("allow_pos", "profile_tail_allow_pos"),
            ("allow_inflection", "profile_tail_allow_inflection"),
            ("allow_variant", "profile_tail_allow_variant"),
            ("allow_pronunciation", "profile_tail_allow_pronunciation"),
            ("allow_descriptor", "profile_tail_allow_descriptor"),
            ("require_selected", "profile_tail_require_selected"),
            ("allow_visual_rescue", "profile_tail_allow_visual_rescue"),
        ):
            setattr(settings, field, bool(tails[short]))
        settings.profile_tail_structure_version = 1
        settings.paddle_allow_strong_edge_visual_rescue = bool(
            tails["allow_visual_rescue"]
        )
        symbols = profile_symbol_inventory_defaults(name)
        settings.profile_symbol_inventory_enabled = bool(symbols["enabled"])
        settings.profile_entry_marker_symbols = " ".join(symbols["entry_markers"])
        settings.profile_bracket_open_symbols = " ".join(symbols["bracket_openers"])
        settings.profile_symbol_visual_rescue_enabled = bool(symbols["visual_rescue"])
        settings.profile_symbol_lane_required = bool(symbols["lane_required"])
        settings.profile_symbol_lane_tolerance_percent = int(symbols["lane_tolerance_percent"])
        settings.profile_symbol_inventory_version = 1
        if name == "cjk_visual":
            entry, bracket, samples = _normalize_cjk_visual_symbol_roles(
                settings.profile_entry_marker_symbols,
                settings.profile_bracket_open_symbols,
                parse_visual_marker_samples(settings.profile_symbol_templates_json),
            )
            settings.profile_entry_marker_symbols = entry
            settings.profile_bracket_open_symbols = bracket
            settings.profile_symbol_templates_json = serialize_visual_marker_samples(samples)
            settings.profile_symbol_template_version = 1
            if not entry:
                settings.profile_allow_marker_prefix = False
        persist()
        refresh()

    heading("词头结构")
    combo = ttk.Combobox(
        row(), textvariable=preset_var, values=tuple(keys),
        state="readonly",
    )
    combo.pack(fill="x", expand=True)
    combo.bind("<<ComboboxSelected>>", choose_preset)
    for title, name, group in HEADWORD_CHECKS:
        add_check(title, name, group)

    divider()
    heading("词后结构")
    for title, name, group in TAIL_CHECKS:
        add_check(title, name, group)

    divider()
    add_check(*SYMBOL_CHECKS[0])
    add_symbols("profile_entry_marker_symbols", "独立入口标记")
    add_symbols("profile_bracket_open_symbols", "括号词头起始")
    for title, name, group in SYMBOL_CHECKS[1:]:
        add_check(title, name, group)
    add_number(*NUMBER_FIELDS[0][0:2], NUMBER_FIELDS[0][5])

    divider()
    heading("词头专属性（当前结构的视觉证据）")
    for name, label, _min, _max, _int, unit in NUMBER_FIELDS[1:5]:
        add_number(name, label, unit)
    heading("CJK单字/括号词附加条件")
    for title, name, group in CJK_CHECKS:
        add_check(title, name, group)
    add_number(NUMBER_FIELDS[5][0], NUMBER_FIELDS[5][1], NUMBER_FIELDS[5][5])

    panel.refresh_from_settings = refresh  # type: ignore[attr-defined]
    refresh()
    return panel
