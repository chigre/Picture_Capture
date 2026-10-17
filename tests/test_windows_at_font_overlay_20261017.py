"""Windows GDI @-vertical font faces must never rotate CJK words in Tk editors."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture import ui_compat


@pytest.mark.parametrize("saved,expected", [
    ("@SimSun", "SimSun"),
    (" @Microsoft JhengHei ", "Microsoft JhengHei"),
    ("@@MingLiU", "MingLiU"),
    ("SimSun", "SimSun"),
    ("自动（系统推荐）", ui_compat.AUTO_FONT_FAMILY),
])
def test_legacy_at_fonts_are_canonicalized_to_horizontal_font_family(saved, expected):
    assert ui_compat.normalize_content_font_setting(saved) == expected


def test_resolver_never_chooses_at_vertical_faces_from_windows(monkeypatch):
    monkeypatch.setattr(
        ui_compat.tkfont, "families",
        lambda widget: ("@SimSun", "SimSun", "@MingLiU", "MingLiU", "Arial"),
    )
    sentinel = SimpleNamespace(actual=lambda name: "@SimSun")
    monkeypatch.setattr(
        ui_compat.tkfont, "nametofont", lambda name, **kwargs: sentinel,
    )
    for configured, expected in (("@SimSun", "SimSun"), ("@MingLiU", "MingLiU")):
        assert ui_compat.resolve_content_font_family(
            object(), configured, "chi_tra",
        ) == expected
    assert ui_compat.preferred_font_family(
        object(), ["@SimSun", "@MingLiU"],
    ) == "SimSun"


def test_vertical_only_face_is_never_passed_to_tk_as_at_font(monkeypatch):
    monkeypatch.setattr(ui_compat.tkfont, "families", lambda widget: ("@SimSun",))
    sentinel = SimpleNamespace(actual=lambda name: "@SimSun")
    monkeypatch.setattr(ui_compat.tkfont, "nametofont", lambda name, **kwargs: sentinel)
    assert not ui_compat.resolve_content_font_family(
        object(), "@SimSun", "chi_tra",
    ).startswith("@")


def test_both_font_menus_hide_windows_at_faces():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    compact = (root / "ui" / "compact_display_menu.py").read_text(encoding="utf-8")
    settings = (root / "app.py").read_text(encoding="utf-8")
    assert 'if not f.startswith("@")' in compact
    assert 'if not f.startswith("@")' in settings


def test_horizontal_entry_widget_remains_selected_from_reading_mode():
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "ui" / "entry_overlay_builder.py"
    ).read_text(encoding="utf-8")
    assert 'horizontal = self.settings.layout_writing_mode == "horizontal-tb"' in src
    assert "if horizontal:\n        editor = tk.Entry(" in src
    assert "editor_font = _entry_font_spec(" in src
