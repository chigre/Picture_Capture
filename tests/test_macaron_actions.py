"""Macaron colour and theme-switch regression tests for main shortcuts."""
from types import SimpleNamespace

from picture_capture.ui import workspace_tools as ui


def test_approved_macaron_palette_is_shared_across_light_and_dark():
    expected = {
        "普": (("#BFDCF2", "#254B69"), ("#355A75", "#EAF5FF")),
        "O": (("#E3CEF6", "#583976"), ("#604A7A", "#F6EBFF")),
        "校": (("#C4EAD8", "#245C47"), ("#376A58", "#E9FFF3")),
    }
    for label, (light, dark) in expected.items():
        assert ui._macaron_action_colors(label, "light")[:2] == light
        assert ui._macaron_action_colors(label, "dark")[:2] == dark
        assert ui._macaron_action_colors(label, "system")[:2] == light


def test_button_theme_refresh_and_hover_preserve_role_and_original_command(monkeypatch):
    class FakeButton:
        def __init__(self, parent, **options):
            self.parent = parent
            self.options = dict(options)
            self.bindings = {}
            self.alive = True

        def bind(self, sequence, callback, add=None):
            self.bindings[sequence] = callback

        def winfo_exists(self):
            return int(self.alive)

        def configure(self, **options):
            self.options.update(options)

    monkeypatch.setattr(ui.tk, "Button", FakeButton)
    app = SimpleNamespace(appearance_mode="light")
    events = []
    buttons = [
        ui._create_macaron_action_button(app, None, label, lambda n=label: events.append(n))
        for label in ("普", "O", "校")
    ]
    assert len(app.workspace_macaron_buttons) == 3
    for button, label in zip(buttons, ("普", "O", "校")):
        assert button.options["bg"] == ui.MACARON_ACTION_COLORS[label]["light"][0]
        assert button.options["anchor"] == "center"
        assert button.options["justify"] == "center"
        assert button._pc_skip_classic_appearance is True
        button.options["command"]()

    assert events == ["普", "O", "校"]
    buttons[0].bindings["<Enter>"](None)
    assert buttons[0].options["bg"] == ui.MACARON_ACTION_COLORS["普"]["light"][2]

    app.appearance_mode = "dark"
    ui.refresh_macaron_action_buttons(app)
    for button, label in zip(buttons, ("普", "O", "校")):
        light_bg, dark_bg = (
            ui.MACARON_ACTION_COLORS[label]["light"][0],
            ui.MACARON_ACTION_COLORS[label]["dark"][0],
        )
        assert light_bg != dark_bg
        assert button.options["fg"] == ui.MACARON_ACTION_COLORS[label]["dark"][1]
        assert button.options["activebackground"] == ui.MACARON_ACTION_COLORS[label]["dark"][2]
    assert buttons[0].options["bg"] == ui.MACARON_ACTION_COLORS["普"]["dark"][2]
    buttons[0].bindings["<Leave>"](None)
    assert buttons[0].options["bg"] == ui.MACARON_ACTION_COLORS["普"]["dark"][0]

    app.appearance_mode = "light"
    ui.refresh_macaron_action_buttons(app)
    assert all(button.options["bg"] ==
               ui.MACARON_ACTION_COLORS[label]["light"][0]
               for button, label in zip(buttons, ("普", "O", "校")))
    buttons[1].alive = False
    ui.refresh_macaron_action_buttons(app)


def test_header_footer_use_same_palette_and_keep_their_callbacks():
    from pathlib import Path
    import picture_capture.app as app_module

    source = Path(ui.__file__).read_text(encoding="utf-8")
    main = Path(app_module.__file__).read_text(encoding="utf-8")
    assert 'app.workspace_macaron_buttons = []' in source
    assert '_create_macaron_action_button(\n            app, quick_host, ("普", "O", "校")[index], command,' in source
    assert '_create_macaron_action_button(app, host, label, callback)' in source
    assert '("普通画线", app.run_normal_draw_action)' in source
    assert '("OCR画线", app.run_ocr_draw_action)' in source
    assert '("词条校对", app.open_review)' in source
    for command in ("app.run_normal_draw_action", "app.run_ocr_draw_action", "app.open_review"):
        assert command in source
    assert 'button._pc_skip_classic_appearance = True' in source
    assert 'refresh_macaron_action_buttons(self)' in main
    assert main.index('refresh_macaron_action_buttons(self)') > main.index(
        'def _apply_resolved_appearance(self, mode: object)'
    )
