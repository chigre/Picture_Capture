from pathlib import Path

from PIL import Image

from picture_capture.appearance import (
    _dark_option_value,
    appearance_palette,
    apply_native_titlebar_appearance,
    normalize_appearance_mode,
    themed_display_image,
)


ROOT = Path(__file__).resolve().parents[1]


def test_normalize_appearance_mode_is_conservative() -> None:
    assert normalize_appearance_mode("dark") == "dark"
    assert normalize_appearance_mode(" DARK ") == "dark"
    assert normalize_appearance_mode("light") == "light"
    assert normalize_appearance_mode("system") == "light"
    assert normalize_appearance_mode(None) == "light"


def test_dark_display_transform_preserves_source_and_reverses_paper_contrast() -> None:
    source = Image.new("RGB", (3, 1))
    source.putdata([(255, 255, 255), (0, 0, 0), (255, 0, 0)])
    before = [source.getpixel((x, 0)) for x in range(3)]

    rendered = themed_display_image(source, "dark")

    assert [source.getpixel((x, 0)) for x in range(3)] == before
    assert rendered is not source
    white_paper, black_print, red_ink = [rendered.getpixel((x, 0)) for x in range(3)]
    assert max(white_paper) <= 40
    assert min(black_print) >= 220
    # Saturated artwork keeps its hue identity instead of becoming a cyan
    # photographic negative.
    assert red_ink[0] > red_ink[1] + 100
    assert red_ink[0] > red_ink[2] + 100


def test_dark_display_transform_preserves_alpha() -> None:
    source = Image.new("RGBA", (2, 1))
    source.putdata([(255, 255, 255, 17), (0, 0, 0, 231)])

    rendered = themed_display_image(source, "dark")

    assert rendered.mode == "RGBA"
    assert [rendered.getpixel((x, 0))[3] for x in range(2)] == [17, 231]
    assert [source.getpixel((x, 0))[3] for x in range(2)] == [17, 231]


def test_light_display_path_is_zero_copy() -> None:
    source = Image.new("RGB", (2, 2), "white")
    assert themed_display_image(source, "light") is source


def test_dark_palette_has_clear_text_background_separation() -> None:
    palette = appearance_palette("dark")

    def luminance(hex_color: str) -> float:
        rgb = tuple(int(hex_color[index:index + 2], 16) / 255.0 for index in (1, 3, 5))
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]

    assert luminance(palette["text"]) - luminance(palette["surface"]) > 0.60
    assert luminance(palette["input_fg"]) - luminance(palette["input_bg"]) > 0.65


def test_classic_spinbox_state_surfaces_use_dark_input_and_button_colors() -> None:
    class FakeWidget:
        @staticmethod
        def winfo_rgb(value: str) -> tuple[int, int, int]:
            text = value.lstrip("#")
            return tuple(int(text[index:index + 2], 16) * 257 for index in (0, 2, 4))

    widget = FakeWidget()
    palette = appearance_palette("dark")

    assert _dark_option_value(
        widget, "disabledbackground", "#ffffff",
        widget_class="Spinbox", palette=palette,
    ) == palette["input_bg"]
    assert _dark_option_value(
        widget, "readonlybackground", "#ffffff",
        widget_class="Spinbox", palette=palette,
    ) == palette["input_bg"]
    assert _dark_option_value(
        widget, "buttonbackground", "#f0f0f0",
        widget_class="Spinbox", palette=palette,
    ) == palette["button"]


def test_native_titlebar_helper_is_safe_off_windows(monkeypatch) -> None:
    import picture_capture.appearance as appearance

    class UnexpectedWindowAccess:
        def __getattr__(self, name: str):
            raise AssertionError(f"native window should not be touched off Windows: {name}")

    monkeypatch.setattr(appearance.sys, "platform", "linux")
    apply_native_titlebar_appearance(UnexpectedWindowAccess(), "dark")


def test_dark_mode_is_integrated_without_changing_project_image_semantics() -> None:
    app_source = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    profile_source = (ROOT / "src/picture_capture/profile_setup.py").read_text(encoding="utf-8")

    assert '"appearance_mode": self.appearance_mode' in app_source
    assert 'key = (id(self.image), int(size[0]), int(size[1]), binary, self.appearance_mode)' in app_source
    assert 'display = themed_display_image(display, self.appearance_mode)' in app_source
    assert 'normalize_appearance_mode(preloaded.get("appearance_mode")) == self.appearance_mode' in app_source
    assert 'appearance_mode = self.appearance_mode' in app_source
    assert 'self._recent_projects_rebuild = rebuild' in app_source
    assert 'getattr(event, "widget", None) is not dialog' in app_source
    assert '"*TCombobox*Listbox.background"' in app_source
    assert '"*TCombobox*Listbox.selectBackground"' in app_source
    assert 'apply_native_titlebar_appearance(root, self.appearance_mode)' in app_source
    assert 'if isinstance(widget, tk.Toplevel)' in app_source
    assert 'button._pc_skip_classic_appearance = True' in app_source
    assert 'activebackground=colors["accent_soft"]' in app_source
    assert 'highlightthickness=0, takefocus=False' in app_source
    assert 'self.parent_app._apply_current_appearance(self)' in app_source
    assert 'word_list_default_fg = palette["input_fg"]' in app_source
    assert 'background="#d9d9d9", foreground="#111827"' in app_source
    assert 'editor_frame._pc_skip_classic_appearance = True' in app_source
    assert 'editor._pc_skip_classic_appearance = True' in app_source
    assert 'selectbackground="#c7d5e3"' in app_source
    assert 'foreground="#111827"' in app_source
    assert 'self._apply_current_appearance(dialog)' in app_source
    assert 'themed_display_image(crop, self.parent.appearance_mode)' in app_source
    assert 'themed_display_image(rendered, self.parent.appearance_mode)' in app_source
    assert "themed_display_image(" in profile_source
    assert 'preview, getattr(self.parent, "appearance_mode", "light")' in profile_source
    assert 'display, getattr(self.parent, "appearance_mode", "light")' in profile_source
