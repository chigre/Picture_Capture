from __future__ import annotations

from picture_capture.models import AppSettings
from picture_capture.profile_indent_ui import (
    INDENT_SEMANTICS_VERSION,
    INDENT_TYPE_CHOICES,
    apply_indent_type_label,
    indent_type_label,
)


def test_indent_type_choices_are_user_level_layout_semantics():
    assert INDENT_TYPE_CHOICES == ("词头缩进", "正文缩进", "无明显缩进")


def test_indent_type_defaults_to_headword_indent():
    settings = AppSettings()
    assert indent_type_label(settings) == "词头缩进"


def test_legacy_brackets_in_body_bit_is_not_reinterpreted_as_body_indent():
    settings = AppSettings()
    settings.profile_cjk_brackets_in_body = True
    settings.profile_parser_controls_version = 1

    assert indent_type_label(settings) == "词头缩进"


def test_indent_type_round_trips_after_explicit_v3_choice():
    settings = AppSettings()
    apply_indent_type_label(settings, "正文缩进")

    assert settings.profile_parser_controls_version >= INDENT_SEMANTICS_VERSION
    assert settings.profile_cjk_brackets_in_body is True
    assert indent_type_label(settings) == "正文缩进"

    apply_indent_type_label(settings, "无明显缩进")
    assert settings.profile_cjk_brackets_in_body is None
    assert indent_type_label(settings) == "无明显缩进"

    apply_indent_type_label(settings, "词头缩进")
    assert settings.profile_cjk_brackets_in_body is False
    assert indent_type_label(settings) == "词头缩进"
