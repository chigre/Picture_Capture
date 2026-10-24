"""Round 18: configured symbol inventory remains role-aware and patchable."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from picture_capture import paddle_headwords_core as core
from picture_capture.ocr import symbol_inventory


def _profile():
    return SimpleNamespace(
        symbol_inventory={
            "entry_markers": ["○"], "bracket_openers": ["【"],
            "visual_families": ["bracket_open"],
        },
        entry_leading_symbols=("○",),
        uses_parser=lambda name: name in {"cjk_marker_pinyin", "cjk_bracketed"},
    )


def _settings(**overrides):
    defaults = dict(
        profile_parser_controls_version=1,
        profile_allow_marker_prefix=True,
        profile_cjk_allow_bracketed_headword=True,
        profile_symbol_inventory_version=1,
        profile_symbol_inventory_enabled=True,
        profile_entry_marker_symbols="◆",
        profile_bracket_open_symbols="【",
        profile_symbol_visual_rescue_enabled=True,
        profile_symbol_lane_required=True,
        profile_symbol_lane_tolerance_percent=50,
        profile_symbol_template_version=0,
        profile_symbol_template_mode="combined",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_marker_inventory_disabled_does_not_disable_brackets():
    settings = _settings(profile_symbol_inventory_enabled=False)
    result = core._configured_symbol_inventory(settings, _profile())
    assert result["entry_markers"] == ()
    assert result["bracket_openers"] == ("【",)
    assert result["marker_role_enabled"] is True
    assert result["bracket_role_enabled"] is True
    assert result["enabled"] is True
    assert result["standalone_inventory_enabled"] is False
    assert core._configured_symbol_inventory.__module__ == "picture_capture.paddle_headwords_core"


def test_symbol_inventory_uses_current_core_parser_templates_and_families(monkeypatch):
    monkeypatch.setattr(core, "_split_configured_symbols", lambda text: ("●",) if text == "◆" else ("〔",))
    monkeypatch.setattr(core, "visual_marker_samples_from_settings", lambda _settings: [
        {"role": "entry_marker", "tag": "marker"},
        {"role": "bracket_open", "tag": "bracket"},
        {"role": "other", "tag": "drop"},
    ])
    monkeypatch.setattr(core, "_SYMBOL_FAMILY_BY_LITERAL", {"●": "circle_filled", "〔": "bracket_open"})
    settings = _settings(profile_symbol_template_version=1)
    got = core._configured_symbol_inventory(settings, _profile())
    expected = symbol_inventory.configured_symbol_inventory(
        settings, _profile(),
        split_symbols_fn=core._split_configured_symbols,
        visual_samples_fn=core.visual_marker_samples_from_settings,
        symbol_families=core._SYMBOL_FAMILY_BY_LITERAL,
    )
    assert got == expected
    assert got["entry_markers"] == ("●",)
    assert got["bracket_openers"] == ("〔",)
    assert set(got["visual_families"]) == {"bracket_open", "circle_filled"}
    assert [v["tag"] for v in got["visual_templates"]] == ["marker", "bracket"]


def test_round18_files_are_owned_below_ocr_not_root():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(pkg.glob("*.py"))) == 10
    for file in ("symbol_inventory.py", "source_candidate_coordinates.py", "review_anchor_variants.py"):
        assert (pkg / "ocr" / file).is_file()
        assert not (pkg / file).exists()
