"""Independent display-line and postproduction crop width contracts."""
from types import SimpleNamespace

from PIL import Image

from picture_capture.models import AppSettings, Entry
import picture_capture.processing_core as core


def test_lined_png_crop_depends_on_crop_width_not_canvas_ratio(monkeypatch):
    image = Image.new("RGB", (400, 200), "white")
    geometry = SimpleNamespace(
        source_to_canonical=lambda x, y: (int(x), int(y)),
        column_widths=[200],
        column_starts=[100],
        x_at=lambda column, y: 100,
        source_size=(400, 200),
        transform=SimpleNamespace(
            canonical_size=lambda size: size,
            canonical_box_to_source=lambda box, size: box,
        ),
    )
    monkeypatch.setattr(core, "column_index", lambda *_: 0)
    entry = Entry(word="A", x=100, y=40)
    settings = AppSettings(
        character_height=18,
        row_padding=2,
        right_ratio=25.0,
        crop_width_percent=50.0,
    )

    initial = core.line_box(entry, geometry, image, settings)
    assert initial == (50, 38, 200, 60)

    settings.right_ratio = 95.0
    assert core.line_box(entry, geometry, image, settings) == initial

    settings.crop_width_percent = 30.0
    assert core.line_box(entry, geometry, image, settings) == (50, 38, 160, 60)
    image.close()


def test_width_fields_are_independent_and_default_to_full_column():
    settings = AppSettings()
    assert settings.right_ratio == settings.crop_width_percent == 100.0
    settings.right_ratio = 42.0
    assert settings.crop_width_percent == 100.0
    settings.crop_width_percent = 17.0
    assert settings.right_ratio == 42.0
