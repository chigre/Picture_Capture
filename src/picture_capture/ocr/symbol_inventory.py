"""Dictionary Profile fixed-symbol inventory policy.

The OCR core passes its mutable parser, visual template and symbol-family
callbacks on every invocation so existing public patch points are preserved.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import AppSettings
    from ..profile.dictionary import DictionaryProfile


def configured_symbol_inventory(
    settings: AppSettings, profile: DictionaryProfile,
    *,
    split_symbols_fn: Any,
    visual_samples_fn: Any,
    symbol_families: dict[str, str],
) -> dict[str, Any]:
    """Resolve dictionary-specific symbol roles with Project Profile overrides.

    Standalone entry markers (○/●/◆...) and bracket openers are separate roles.
    The historical profile_symbol_inventory_enabled switch now controls only
    the standalone-marker inventory. Bracket openers remain active whenever
    the user enabled the explicit bracket-headword structure; otherwise a
    configured bracket opener/template can be silently disabled merely because
    the dictionary has no standalone marker prefix.
    """
    _split_configured_symbols = split_symbols_fn
    visual_marker_samples_from_settings = visual_samples_fn
    _SYMBOL_FAMILY_BY_LITERAL = symbol_families

    base = dict(profile.symbol_inventory or {})
    has_role_aware_inventory = bool(profile.symbol_inventory is not None)
    entry = tuple(str(x) for x in base.get("entry_markers", []) if str(x))
    if not entry and not has_role_aware_inventory:
        entry = tuple(str(x) for x in profile.entry_leading_symbols if str(x))
    bracket = tuple(str(x) for x in base.get("bracket_openers", []) if str(x))

    parser_controls = int(
        getattr(settings, "profile_parser_controls_version", 0) or 0
    ) >= 1
    marker_role_enabled = (
        bool(getattr(settings, "profile_allow_marker_prefix", False))
        if parser_controls else profile.uses_parser("cjk_marker_pinyin")
    )
    bracket_role_enabled = (
        bool(getattr(settings, "profile_cjk_allow_bracketed_headword", True))
        if parser_controls else profile.uses_parser("cjk_bracketed")
    )

    saved = int(getattr(settings, "profile_symbol_inventory_version", 0) or 0) >= 1
    if saved:
        marker_inventory_enabled = bool(
            getattr(settings, "profile_symbol_inventory_enabled", True)
        )
        entry = (
            _split_configured_symbols(
                getattr(settings, "profile_entry_marker_symbols", "")
            )
            if marker_inventory_enabled and marker_role_enabled else ()
        )
        # Bracket structure has its own explicit checkbox and must not be
        # disabled by the standalone-marker switch.
        bracket = (
            _split_configured_symbols(
                getattr(settings, "profile_bracket_open_symbols", "")
            )
            if bracket_role_enabled else ()
        )
        visual_rescue = bool(
            getattr(settings, "profile_symbol_visual_rescue_enabled", True)
        )
        lane_required = bool(
            getattr(settings, "profile_symbol_lane_required", True)
        )
        lane_tolerance = max(
            20, min(
                120,
                int(getattr(settings, "profile_symbol_lane_tolerance_percent", 50) or 50),
            )
        )
    else:
        marker_inventory_enabled = bool(base.get("enabled", True))
        visual_rescue = bool(base.get("visual_rescue", True))
        lane_required = bool(base.get("lane_expected", False))
        lane_tolerance = max(
            20, min(120, int(base.get("lane_tolerance_percent") or 50))
        )
        if not marker_role_enabled:
            entry = ()
        if not bracket_role_enabled:
            bracket = ()
        if (
            not entry
            and parser_controls
            and marker_role_enabled
            and marker_inventory_enabled
        ):
            entry = ("○", "●", "◦", "•", "〓", "◆", "◇", "►", "▶")

    template_mode = str(
        getattr(settings, "profile_symbol_template_mode", "combined") or "combined"
    )
    if template_mode not in {"off", "combined", "template_first"}:
        template_mode = "combined"
    group_mode = str(
        getattr(settings, "profile_symbol_template_group_mode", "role") or "role"
    )
    if group_mode not in {"role", "literal"}:
        group_mode = "role"
    template_threshold = max(
        0.35,
        min(
            0.95,
            float(getattr(settings, "profile_symbol_template_threshold", 0.68) or 0.68),
        ),
    )
    templates = (
        visual_marker_samples_from_settings(settings)
        if int(getattr(settings, "profile_symbol_template_version", 0) or 0) >= 1
        and template_mode != "off"
        else []
    )
    templates = [
        sample for sample in templates
        if (
            str(sample.get("role") or "") == "bracket_open"
            and bracket_role_enabled
        ) or (
            str(sample.get("role") or "") == "entry_marker"
            and marker_inventory_enabled
            and marker_role_enabled
        )
    ]

    effective_enabled = bool(
        (marker_inventory_enabled and marker_role_enabled and entry)
        or (bracket_role_enabled and bracket)
        or templates
    )
    families = {
        _SYMBOL_FAMILY_BY_LITERAL[symbol]
        for symbol in entry + bracket
        if symbol in _SYMBOL_FAMILY_BY_LITERAL
    }
    for family in (str(x) for x in base.get("visual_families", []) if str(x)):
        if family == "bracket_open" and bracket_role_enabled:
            families.add(family)
        elif (
            family != "bracket_open"
            and marker_inventory_enabled
            and marker_role_enabled
        ):
            families.add(family)

    return {
        "enabled": effective_enabled,
        "standalone_inventory_enabled": marker_inventory_enabled,
        "marker_role_enabled": marker_role_enabled,
        "bracket_role_enabled": bracket_role_enabled,
        "entry_markers": entry,
        "bracket_openers": bracket,
        "visual_rescue": visual_rescue,
        "lane_required": lane_required,
        "lane_tolerance_percent": lane_tolerance,
        "visual_families": tuple(sorted(families)),
        "visual_templates": templates,
        "visual_template_mode": template_mode,
        "visual_template_group_mode": group_mode,
        "visual_template_threshold": template_threshold,
    }
