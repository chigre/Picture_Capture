"""Layout-aware quick actions never write traditional PDIC on spatial pages."""
from pathlib import Path
from types import SimpleNamespace

from picture_capture.models import AppSettings
from picture_capture.ui.illustrated_action_router import run_page_quick_action


class Status:
    def __init__(self):
        self.message = ""
    def set(self, message):
        self.message = str(message)


def test_quick_actions_preserve_traditional_callbacks():
    events = []
    app = SimpleNamespace(settings=AppSettings(), current_page=Path("0001.png"),
                          status_var=Status())
    assert run_page_quick_action(app, "ocr", lambda: events.append("traditional")) is None
    assert events == ["traditional"]
    app.settings.dictionary_layout_kind = "mixed"
    assert run_page_quick_action(app, "open", lambda: events.append("again")) is None
    assert events == ["traditional", "again"]


def test_spatial_save_avoids_traditional_pdic_writes():
    events = []
    app = SimpleNamespace(settings=AppSettings(dictionary_layout_kind="illustrated"),
                          current_page=Path("0001.png"), status_var=Status())
    run_page_quick_action(app, "save", lambda: events.append("PDIC_WRITTEN"))
    assert events == []
    assert "即时保存" in app.status_var.message


def test_quick_action_routes_mixed_page_by_filename(monkeypatch):
    from picture_capture.ui import illustrated_dictionary_window as window
    events = []
    monkeypatch.setattr(window, "open_illustrated_dictionary_editor",
                        lambda _app, *, action: events.append(action))
    settings = AppSettings(
        dictionary_layout_kind="mixed",
        illustrated_page_overrides={"0001.png": "illustrated"},
    )
    app = SimpleNamespace(settings=settings, current_page=Path("0001.png"),
                          status_var=Status())
    run_page_quick_action(app, "ocr", lambda: events.append("traditional"))
    assert events == ["detect"]
    app.current_page = Path("0002.png")
    run_page_quick_action(app, "ocr", lambda: events.append("traditional"))
    assert events == ["detect", "traditional"]


def test_profile_wizard_has_mode_selector_and_guards_ordinary_layout_scan():
    path = (Path(__file__).resolve().parents[1] / "src" / "picture_capture" /
            "profile_setup.py")
    text = path.read_text(encoding="utf-8")
    assert "add_wizard_layout_selector(self, tab, row=6)" in text
    assert 'self.working.dictionary_layout_kind != "illustrated"' in text
