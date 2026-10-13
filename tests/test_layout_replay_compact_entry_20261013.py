"""Regression: the *visible* 280px display palette must expose Layout replay.

The old quick-settings section is hidden when compact mode is active.  A
control existing only in that section is not a user-accessible feature.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.layout_visualization_ui_v3 import toggle_layout_step_replay


ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


class Flag:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_actual_compact_display_palette_has_session_only_replay_toggle():
    compact = (ROOT / "ui" / "compact_display_menu.py").read_text(encoding="utf-8")
    legacy = (ROOT / "layout_visualization_ui_v3.py").read_text(encoding="utf-8")
    workspace = (ROOT / "ui" / "workspace_tools.py").read_text(encoding="utf-8")
    assert 'sections["二、显示设置"] = build_compact_display_menu(app, content)' in workspace
    assert 'replay_var = app._layout_step_replay_var' in compact
    assert 'check(row, "查看 LAYOUT 分析过程", replay_var, toggle_replay)' in compact
    assert 'text="查看 LAYOUT 分析过程"' in legacy
    assert 'command=lambda: toggle_layout_step_replay(app)' in legacy
    assert compact.index('check(row, "显示Layout"') < compact.index(
        'check(row, "查看 LAYOUT 分析过程"'
    ) < compact.index('label(row, "Layout叠加")')
    assert 'app.quick_bool_vars["layout_step_replay"]' not in compact


def test_compact_and_legacy_share_window_lifecycle(monkeypatch):
    from picture_capture import layout_step_replay_ui as replay

    calls = []
    flag = Flag(True)
    window = SimpleNamespace(close=lambda: calls.append("closed"))
    app = SimpleNamespace(
        _layout_step_replay_var=flag,
        _layout_step_replay_window=None,
    )
    monkeypatch.setattr(replay, "show_layout_step_replay", lambda current: calls.append(current))
    toggle_layout_step_replay(app)
    assert calls == [app]
    app._layout_step_replay_window = window
    flag.set(False)
    toggle_layout_step_replay(app)
    assert calls[-1] == "closed"


def test_replay_open_failure_resets_shared_checkbox(monkeypatch):
    from picture_capture import layout_step_replay_ui as replay

    def broken(_app):
        raise RuntimeError("dialog unavailable")

    monkeypatch.setattr(replay, "show_layout_step_replay", broken)
    flag = Flag(True)
    app = SimpleNamespace(_layout_step_replay_var=flag)
    with pytest.raises(RuntimeError, match="dialog unavailable"):
        toggle_layout_step_replay(app)
    assert flag.get() is False


def test_disabled_replay_is_noop_without_window(monkeypatch):
    from picture_capture import layout_step_replay_ui as replay

    monkeypatch.setattr(
        replay, "show_layout_step_replay",
        lambda _app: pytest.fail("disabled replay must not open a window"),
    )
    app = SimpleNamespace(_layout_step_replay_var=Flag(False))
    assert toggle_layout_step_replay(app) is None
