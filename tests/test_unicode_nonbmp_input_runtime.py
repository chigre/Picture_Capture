from pathlib import Path

from picture_capture.unicode_nonbmp_input_runtime import (
    TextSnapshot,
    contains_non_bmp,
    legacy_tk_renderings,
    plan_non_bmp_repair,
)


RARE_CJK = "𨤆"  # U+28906, CJK Unified Ideographs Extension B


def test_reported_character_is_non_bmp_extension_b():
    assert ord(RARE_CJK) == 0x28906
    assert contains_non_bmp(RARE_CJK)
    assert not contains_non_bmp("词条")


def test_legacy_tk_rendering_models_windows_surrogate_loss():
    renderings = legacy_tk_renderings(RARE_CJK)
    assert "??" in renderings
    assert "��" in renderings


def test_repair_replaces_question_pair_at_cursor():
    current = TextSnapshot("abc??def", 5)
    repaired = plan_non_bmp_repair(current, RARE_CJK)
    assert repaired == TextSnapshot(f"abc{RARE_CJK}def", 4, None)


def test_repair_restores_commit_that_tk_dropped_entirely():
    previous = TextSnapshot("abc", 3)
    current = TextSnapshot("abc", 3)
    repaired = plan_non_bmp_repair(current, RARE_CJK, previous)
    assert repaired == TextSnapshot(f"abc{RARE_CJK}", 4, None)


def test_repair_preserves_selection_replacement_semantics():
    previous = TextSnapshot("abcXYZdef", 6, (3, 6))
    current = TextSnapshot("abc??def", 5)
    repaired = plan_non_bmp_repair(current, RARE_CJK, previous)
    assert repaired == TextSnapshot(f"abc{RARE_CJK}def", 4, None)


def test_repair_handles_mixed_bmp_and_non_bmp_commit():
    committed = f"甲{RARE_CJK}乙"
    assert "甲??乙" in legacy_tk_renderings(committed)
    current = TextSnapshot("前甲??乙后", 5)
    repaired = plan_non_bmp_repair(current, committed)
    assert repaired == TextSnapshot(f"前{committed}后", 4, None)


def test_already_correct_non_bmp_commit_is_never_duplicated():
    current = TextSnapshot(f"abc{RARE_CJK}", 4)
    assert plan_non_bmp_repair(current, RARE_CJK) is None


def test_bmp_commits_are_outside_compatibility_path():
    current = TextSnapshot("汉", 1)
    assert plan_non_bmp_repair(current, "汉") is None


def test_launcher_installs_nonbmp_bridge_before_app_instances_exist():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "picture_capture" / "launcher.py").read_text(encoding="utf-8")
    assert "from .unicode_nonbmp_input_runtime import install_nonbmp_unicode_input" in source
    assert "install_nonbmp_unicode_input(app_module)" in source
    assert source.index("install_nonbmp_unicode_input(app_module)") < source.index(
        "_PREPARED_APP_MODULE = app_module"
    )
