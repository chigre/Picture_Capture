"""Tk callback boundary for R3 regenerate failures; synthetic text only.

A stale/foreign simplified sidecar must remain protected, but clicking the
regenerate command must not emit an unhandled Tk exception or expose
human source text in a traceback/status.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

app_module = importlib.import_module("picture_capture.app")


class Value:
    def __init__(self, text):
        self.text = text
    def get(self):
        return self.text
    def set(self, text):
        self.text = text


@pytest.mark.parametrize("raised", [
    RuntimeError("R3 简体记录来源词条与 PDIC 原图坐标不一致，拒绝覆盖 private-word"),
    OSError("private path /never-upload/PDIC record failed"),
    ValueError("private old source word"),
])
def test_r3_regenerate_callback_handles_refusal_without_losing_text(monkeypatch, raised):
    notices = []
    deps = SimpleNamespace(
        messagebox=SimpleNamespace(showerror=lambda *args, **kw: notices.append((args, kw))),
    )
    monkeypatch.setattr(app_module, "_review_simplified_deps", lambda: deps)

    def refused(_review, _deps):
        raise raised

    monkeypatch.setattr(
        app_module._review_simplified, "regenerate_simplified_current_page", refused,
    )
    original = Value("private original correction")
    simplified = Value("private manual simplified correction")
    status = Value("previous status")
    review = SimpleNamespace(
        parent=SimpleNamespace(status_var=status),
        vars=[original], simplified_vars=[simplified],
    )
    assert app_module.ReviewWindow.regenerate_simplified_current_page(review) is None
    assert original.get() == "private original correction"
    assert simplified.get() == "private manual simplified correction"
    assert notices and "重新简体化" in notices[0][0][0]
    assert any(word in status.get() for word in ("未保存", "未完成", "未确认"))
    assert all(
        forbidden not in (status.get() + repr(notices))
        for forbidden in ("private", "/never-upload/")
    )


def test_r3_regenerate_healthy_callback_passes_through(monkeypatch):
    calls = []
    deps = SimpleNamespace(messagebox=SimpleNamespace(showerror=lambda *a, **k: calls.append("error")))
    monkeypatch.setattr(app_module, "_review_simplified_deps", lambda: deps)
    monkeypatch.setattr(
        app_module._review_simplified, "regenerate_simplified_current_page",
        lambda review, deps: calls.append((review, deps)),
    )
    review = SimpleNamespace(parent=SimpleNamespace(status_var=Value("")))
    assert app_module.ReviewWindow.regenerate_simplified_current_page(review) is None
    assert calls == [(review, deps)]
