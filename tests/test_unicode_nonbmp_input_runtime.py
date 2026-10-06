import ast
from pathlib import Path
from types import SimpleNamespace

import picture_capture.unicode_nonbmp_input as nonbmp
from picture_capture.unicode_nonbmp_input import (
    attach_nonbmp_unicode_input,
    close_nonbmp_unicode_input,
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


def test_bridge_requirement_is_windows_tk8_only(monkeypatch):
    class TkProxy:
        def __init__(self, patchlevel: str) -> None:
            self.patchlevel = patchlevel

        def call(self, *args):
            assert args == ("info", "patchlevel")
            return self.patchlevel

    monkeypatch.setattr(nonbmp.platform, "system", lambda: "Linux")
    assert not nonbmp._needs_windows_tk8_bridge(SimpleNamespace(tk=TkProxy("8.6.14")))

    monkeypatch.setattr(nonbmp.platform, "system", lambda: "Windows")
    assert nonbmp._needs_windows_tk8_bridge(SimpleNamespace(tk=TkProxy("8.6.14")))
    assert not nonbmp._needs_windows_tk8_bridge(SimpleNamespace(tk=TkProxy("9.0.0")))


def test_attach_is_noop_when_bridge_not_required(monkeypatch):
    app = SimpleNamespace()
    monkeypatch.setattr(nonbmp, "_needs_windows_tk8_bridge", lambda _app: False)
    assert attach_nonbmp_unicode_input(app) is None
    assert app._pc_nonbmp_unicode_bridge is None


def test_attach_once_and_close_are_explicit_and_idempotent(monkeypatch):
    events = []

    class Bridge:
        def __init__(self, app) -> None:
            events.append(("attach", app))
            self.closed = 0

        def close(self) -> None:
            self.closed += 1
            events.append(("close", self.closed))

    app = SimpleNamespace()
    monkeypatch.setattr(nonbmp, "_needs_windows_tk8_bridge", lambda _app: True)
    monkeypatch.setattr(nonbmp, "_WindowsNonBmpBridge", Bridge)

    first = attach_nonbmp_unicode_input(app)
    second = attach_nonbmp_unicode_input(app)
    assert first is second
    assert [kind for kind, _value in events] == ["attach"]

    close_nonbmp_unicode_input(app)
    close_nonbmp_unicode_input(app)
    assert first.closed == 1
    assert app._pc_nonbmp_unicode_bridge is None
    assert [kind for kind, _value in events] == ["attach", "close"]


def test_app_owns_nonbmp_bridge_lifecycle_without_gui_installer():
    root = Path(__file__).resolve().parents[1]
    package = root / "src" / "picture_capture"
    app_source = (package / "app.py").read_text(encoding="utf-8")
    gui_source = (package / "bootstrap" / "gui.py").read_text(encoding="utf-8")
    guard = (root / "scripts" / "architecture_guard.py").read_text(encoding="utf-8")

    assert not (package / "unicode_nonbmp_input_runtime.py").exists()
    assert (package / "unicode_nonbmp_input.py").exists()
    assert "install_nonbmp_unicode_input" not in gui_source
    assert '"unicode_nonbmp_input_runtime.py"' not in guard

    tree = ast.parse(app_source)
    app_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PictureCaptureApp"
    )
    methods = {
        node.name: node
        for node in app_class.body
        if isinstance(node, ast.FunctionDef)
    }
    init_text = ast.get_source_segment(app_source, methods["__init__"]) or ""
    destroy_text = ast.get_source_segment(app_source, methods["destroy"]) or ""
    assert "attach_nonbmp_unicode_input(self)" in init_text
    assert init_text.rstrip().endswith("attach_nonbmp_unicode_input(self)")
    assert "close_nonbmp_unicode_input(self)" in destroy_text
    assert "super().destroy()" in destroy_text
    assert destroy_text.index("close_nonbmp_unicode_input(self)") < destroy_text.index(
        "super().destroy()"
    )
