"""Issue #562: Tk text-report widget assembly has one canonical UI owner."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from picture_capture import app
from picture_capture.ui import main_dialog_lifecycle


class FakeWidget:
    def __init__(self, parent=None, **kwargs):
        self.parent = parent
        self.options = kwargs
        self.calls = []
        self.title_text = None

    def title(self, text):
        self.title_text = text

    def pack(self, **kwargs):
        self.calls.append(("pack", kwargs))

    def grid(self, **kwargs):
        self.calls.append(("grid", kwargs))

    def configure(self, **kwargs):
        self.calls.append(("configure", kwargs))

    def rowconfigure(self, *args, **kwargs):
        self.calls.append(("rowconfigure", args, kwargs))

    def columnconfigure(self, *args, **kwargs):
        self.calls.append(("columnconfigure", args, kwargs))

    def yview(self, *args):
        return None

    def xview(self, *args):
        return None

    def set(self, *args):
        return None

    def insert(self, *args):
        self.calls.append(("insert", args))


def test_report_body_physically_owned_by_ui_not_app() -> None:
    assert "tk.Toplevel(self)" in inspect.getsource(main_dialog_lifecycle.show_text_report)
    assert "tk.Toplevel(self)" not in inspect.getsource(app.PictureCaptureApp._show_text_report)
    assert list(inspect.signature(app.PictureCaptureApp._show_text_report).parameters) == [
        "self", "title", "text",
    ]


def test_report_uses_current_app_tk_font_and_window_hooks(monkeypatch) -> None:
    created = {}
    def factory(kind):
        def make(parent=None, **kwargs):
            widget = FakeWidget(parent, **kwargs)
            created.setdefault(kind, []).append(widget)
            return widget
        return make

    sizing = []
    fonts = []
    monkeypatch.setattr(app, "tk", SimpleNamespace(Toplevel=factory("window"), Text=factory("text")))
    monkeypatch.setattr(app, "ttk", SimpleNamespace(Frame=factory("frame"), Scrollbar=factory("scrollbar")))
    monkeypatch.setattr(app, "fit_window_to_work_area", lambda *a, **kw: sizing.append((a, kw)))
    monkeypatch.setattr(app, "preferred_font_family", lambda *a, **kw: fonts.append((a, kw)) or "Custom Mono")

    parent = object()
    assert app.PictureCaptureApp._show_text_report(parent, "审校报告", "line one\nline two") is None
    assert created["window"][0].parent is parent
    assert created["window"][0].title_text == "审校报告"
    assert sizing[0][1] == {"min_width": 640, "min_height": 460}
    assert sizing[0][0][1:] == (900, 650)
    assert fonts[0][1] == {"fallback_named_font": "TkFixedFont"}
    box = created["text"][0]
    assert box.options["font"] == ("Custom Mono", 11)
    assert ("insert", ("1.0", "line one\nline two")) in box.calls
    assert ("configure", {"state": "disabled"}) in box.calls
    assert len(created["scrollbar"]) == 2
    assert {w.options["orient"] for w in created["scrollbar"]} == {"vertical", "horizontal"}
