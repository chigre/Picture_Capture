from __future__ import annotations

"""Historical AppSettings payload migrations.

This module owns version-to-version transformation of already-decoded settings
payloads. It deliberately does not import AppSettings or models, so the model
layer can call it without creating a reverse dependency.
"""

from collections.abc import Callable
from typing import Any


def migrate_app_settings_payload(
    raw: dict[str, Any],
    defaults_factory: Callable[[], Any],
) -> dict[str, Any]:
    """Upgrade one decoded settings payload while preserving user overrides."""
    if int(raw.get("right_ratio_percent_version", 0) or 0) < 1:
        old_divisor = max(0.01, float(raw.get("right_ratio", 1.0) or 1.0))
        # Preserve the original VB "向右比例 1/x" before migrating the
        # repurposed right_ratio field to the modern entry-box percentage.
        raw.setdefault("ordinary_right_divisor", old_divisor)
        raw["right_ratio"] = 100.0 / old_divisor
        raw["right_ratio_percent_version"] = 1
    # Transparently upgrade the untouched v1.4 default regex. Without this
    # migration, an existing project would keep matching only the first
    # syllable of display forms such as ``a·ga·rrón``. User-customized
    # regexes are left exactly as they are.
    legacy_headword_regex = r"^\s*[•◆◇■□►▶*†‡§¶]?\s*([^\W\d_]+(?:[-'’][^\W\d_]+)*)"
    if raw.get("paddle_headword_regex") == legacy_headword_regex:
        raw["paddle_headword_regex"] = defaults_factory().paddle_headword_regex
        # Also upgrade untouched v1.4 defaults that would otherwise crop
        # long ``lemma (plural) POS`` lines before the grammatical cue.
        if raw.get("paddle_band_width") == 180:
            raw["paddle_band_width"] = defaults_factory().paddle_band_width
        if raw.get("paddle_min_candidate_score") == 4.0:
            # Historical v1.4 migration keeps the v1.5 compatibility target.
            # Fresh v2.3 projects use the new UI/default value 1.0 instead.
            raw["paddle_min_candidate_score"] = 5.0
    # v1.5.x shipped conservative OCR defaults while the real dictionary
    # pages showed that longer headword/POS lines and syllabified bold text
    # benefit from a wider band, lower candidate confidence and looser same-line merge.
    # Upgrade only untouched defaults; explicit user tuning is preserved.
    old_v15_regex = (
        r"^\s*[•◆◇■□►▶*†‡§¶]?\s*"
        r"([^\W\d_]+(?:\s*[·•∙‧]\s*[^\W\d_]+|[.:][^\W\d_]+|[-'’][^\W\d_]+)*)"
    )
    if raw.get("paddle_headword_regex") == old_v15_regex:
        raw["paddle_headword_regex"] = defaults_factory().paddle_headword_regex
    old_v156_regex = (
        r"^\s*[•◆◇■□►▶*†‡§¶]?\s*"
        r"(-?[^\W\d_]+(?:\s*[·•∙‧]\s*[^\W\d_]+|[.:][^\W\d_]+|[-'’][^\W\d_]+)*)"
    )
    if raw.get("paddle_headword_regex") == old_v156_regex:
        raw["paddle_headword_regex"] = defaults_factory().paddle_headword_regex
    old_v158_headword_regex = (
        r"^\s*[•◆◇■□►▶*†‡§¶]?\s*"
        r"(-?[^\W\d_]+(?:\s*[·•∙‧.:+]{1,3}\s*[^\W\d_]+|"
        r"[·•∙‧.:+]*-+[·•∙‧.:+]*[^\W\d_]+|['’][^\W\d_]+)*-?)"
    )
    if raw.get("paddle_headword_regex") == old_v158_headword_regex:
        raw["paddle_headword_regex"] = defaults_factory().paddle_headword_regex
    if raw.get("paddle_band_width") == 420:
        raw["paddle_band_width"] = defaults_factory().paddle_band_width
    if raw.get("paddle_rec_score_threshold") == 0.45:
        raw["paddle_rec_score_threshold"] = defaults_factory().paddle_rec_score_threshold
    if raw.get("paddle_line_merge_y_ratio") == 0.55:
        raw["paddle_line_merge_y_ratio"] = defaults_factory().paddle_line_merge_y_ratio
    if raw.get("paddle_pos_search_chars") == 96:
        raw["paddle_pos_search_chars"] = defaults_factory().paddle_pos_search_chars
    # v1.5.5 did not recognize the dictionary's bare ``s.`` POS label, so
    # entries such as ``agregado, da s.`` and ``agricultor, to·ra s.``
    # could be rejected. Upgrade only the untouched shipped default.
    old_v155_pos_regex = (
        r"(?:s\.?\s*(?:m|f|com|n)\.?|adj\.?\s*(?:inv\.?)?|adv\.?|"
        r"[vy]\.(?:\s*prnl\.?)?|prep\.?|conj\.?|pron\.?|interj\.?|"
        r"art\.?|num\.?|loc\.?|superlat\.?(?:\s*irreg\.?)?)"
    )
    if raw.get("paddle_pos_regex") == old_v155_pos_regex:
        raw["paddle_pos_regex"] = defaults_factory().paddle_pos_regex
    # v1.5.8 still lacked ``s.amb.`` and extended pronoun labels such as
    # ``pron.indef.``. Upgrade only the untouched shipped default.
    old_v158_pos_regex = (
        r"(?:s\.?\s*(?:m|f|com|n)\.?|s\.|adj\.?\s*(?:inv\.?)?|adv\.?|"
        r"[vy]\.(?:\s*prnl\.?)?|prep\.?|conj\.?|pron\.?|interj\.?|"
        r"art\.?|num\.?|loc\.?|superlat\.?(?:\s*irreg\.?)?)"
    )
    if raw.get("paddle_pos_regex") == old_v158_pos_regex:
        raw["paddle_pos_regex"] = defaults_factory().paddle_pos_regex
    old_symbol_regex = r"^\s*[•◆◇■□►▶*†‡§¶]"
    if raw.get("paddle_special_symbol_regex") == old_symbol_regex:
        raw["paddle_special_symbol_regex"] = defaults_factory().paddle_special_symbol_regex
    if raw.get("detection_method") in {"projection", "hybrid"}:
        raw["detection_method"] = "left_edge"
    # v2.5 Spanish-only sort modes migrate to the generalized collation
    # profiles introduced in v2.6.
    if raw.get("headword_sort_mode") == "es_modern":
        raw["headword_sort_mode"] = "spa_modern"
    elif raw.get("headword_sort_mode") == "es_traditional":
        raw["headword_sort_mode"] = "spa_traditional"

    # v2.11.13 changed review typography from ``base size × review zoom``
    # to a fixed font size.  Some established projects therefore carry a
    # deliberately large old base size (for example 72 at 26% zoom gave an
    # actual ~19 pt editor).  Interpreting 72 as the new fixed size makes a
    # one-line Entry look enormous.  Migrate only clearly legacy-large
    # values; ordinary 18-24 pt fixed sizes from v2.11.13 are left intact.
    if int(raw.get("review_font_semantics_version", 1) or 1) < 2:
        try:
            old_size = max(6, int(raw.get("review_entry_font_size", defaults_factory().review_entry_font_size)))
            old_zoom = min(250.0, max(20.0, float(raw.get("review_zoom_percent", 64.0))))
            if old_size > 36 and old_zoom < 100:
                raw["review_entry_font_size"] = max(6, min(48, round(old_size * old_zoom / 100.0)))
        except (TypeError, ValueError):
            pass
        raw["review_font_semantics_version"] = 2

    # v2.12.9 split review typography into independent original-headword
    # and Simplified styles. Existing projects inherit their established
    # headword style on first load so the upgrade does not change display.
    if "review_simplified_font_family" not in raw:
        raw["review_simplified_font_family"] = str(
            raw.get("review_entry_font_family", defaults_factory().review_entry_font_family) or defaults_factory().review_entry_font_family
        )
    if "review_simplified_font_size" not in raw:
        raw["review_simplified_font_size"] = raw.get("review_entry_font_size", defaults_factory().review_entry_font_size)
    if "review_simplified_font_bold" not in raw:
        raw["review_simplified_font_bold"] = bool(raw.get("review_entry_font_bold", defaults_factory().review_entry_font_bold))
    if "review_simplified_font_italic" not in raw:
        raw["review_simplified_font_italic"] = bool(raw.get("review_entry_font_italic", defaults_factory().review_entry_font_italic))

    # v2.12.12: both layout-behavior options become opt-in.  Older projects
    # inherited ``follow_column_deformation=True`` by default and may also
    # have ``manual_columns`` persisted as checked.  Reset them once on the
    # first load after this upgrade; subsequent user choices are preserved.
    if int(raw.get("layout_behavior_defaults_version", 0) or 0) < 1:
        raw["manual_columns"] = False
        raw["follow_column_deformation"] = False
        raw["layout_behavior_defaults_version"] = 1

    # CJK Profile role migration: early Project Profile builds could seed
    # bracket glyphs (especially 【) into the standalone entry-marker role,
    # and visual samples captured from those projects inherited
    # role=entry_marker. Migrate once; later user edits are preserved.
    if int(raw.get("profile_symbol_role_semantics_version", 0) or 0) < 1:
        if str(raw.get("dictionary_profile_id") or "") == "cjk_visual":
            try:
                from .visual_marker_templates import (
                    parse_visual_marker_samples,
                    serialize_visual_marker_samples,
                    split_configured_symbols,
                )

                bracket_role_symbols = set("【〔［[「『〈《")
                entry = list(split_configured_symbols(
                    raw.get("profile_entry_marker_symbols", "")
                ))
                bracket = list(split_configured_symbols(
                    raw.get("profile_bracket_open_symbols", "")
                ))
                bracket_set = set(bracket)
                moved = [
                    symbol for symbol in entry
                    if symbol in bracket_role_symbols
                    or symbol in bracket_set
                ]
                entry = [
                    symbol for symbol in entry
                    if symbol not in moved
                ]
                bracket = list(dict.fromkeys([*bracket, *moved]))
                if (
                    bool(raw.get(
                        "profile_cjk_allow_bracketed_headword", True
                    ))
                    and not bracket
                ):
                    bracket = ["【"]
                raw["profile_entry_marker_symbols"] = " ".join(entry)
                raw["profile_bracket_open_symbols"] = " ".join(bracket)
                if not entry:
                    raw["profile_allow_marker_prefix"] = False
                # If we actually had to move a bracket out of the old
                # entry-marker role, that project was created under the
                # buggy semantics. Reset visual rescue to the new safe
                # opt-in default; direct OCR bracket parsing remains on.
                if moved:
                    raw["profile_symbol_visual_rescue_enabled"] = False
                # Stable lane evidence remains the required safety net if
                # the user later turns bracket visual rescue back on.
                raw["profile_symbol_lane_required"] = True

                samples = parse_visual_marker_samples(
                    raw.get("profile_symbol_templates_json", "")
                )
                bracket_set = set(bracket)
                migrated_samples = []
                for sample in samples:
                    item = dict(sample)
                    literal = str(item.get("literal") or "")
                    if (
                        str(item.get("role") or "") == "entry_marker"
                        and literal in bracket_set
                    ):
                        item["role"] = "bracket_open"
                    migrated_samples.append(item)
                raw["profile_symbol_templates_json"] = (
                    serialize_visual_marker_samples(migrated_samples)
                )
            except Exception:
                # Settings loading must remain robust even if a malformed
                # old visual-template payload cannot be migrated.
                pass
        raw["profile_symbol_role_semantics_version"] = 1

    # v2.14: make the recommended OCR path single-engine by default and
    # declutter the page list. Apply once to existing projects so persisted
    # historical defaults do not mask the new UI defaults; later user edits
    # are preserved because the version marker is then saved as 1.
    if int(raw.get("ui_workflow_defaults_version", 0) or 0) < 1:
        raw["paddle_use_paddleocr"] = True
        raw["paddle_compare_tesseract"] = False
        raw["paddle_dual_ocr_arbitration"] = False
        raw["page_list_show_fill_status"] = False
        raw["ui_workflow_defaults_version"] = 1

    # Project Profile A/B page-edge widths were split after the original
    # single profile_side_percent setting. Existing projects inherit their
    # established width for both variants on first load.
    legacy_side_percent = raw.get("profile_side_percent", defaults_factory().profile_side_percent)
    raw.setdefault("profile_side_percent_a", legacy_side_percent)
    raw.setdefault("profile_side_percent_b", legacy_side_percent)

    return raw


__all__ = ["migrate_app_settings_payload"]
