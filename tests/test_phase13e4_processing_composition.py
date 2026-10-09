"""Phase 13E4: processing delegates full understanding to composed service."""
from PIL import Image

from picture_capture import layout_composition
from picture_capture import processing
from picture_capture.models import AppSettings


def test_processing_full_understanding_calls_explicit_service(monkeypatch):
    calls = []
    marker = object()

    def composed(image, settings, *, page_index=0, page_sections=None):
        calls.append((image, settings, page_index, page_sections))
        return marker

    monkeypatch.setattr(layout_composition, "understand_composed_page", composed)
    settings = AppSettings()
    settings.layout_mask_illustrations = False
    image = Image.new("RGB", (40, 30), "white")
    sections = []
    output = processing._understand_page_current(
        image, settings, page_index=3,
        page_sections=sections, layout_only=False,
    )
    assert output is marker
    assert calls == [(image, settings, 3, sections)]


def test_processing_layout_only_still_uses_layout_core(monkeypatch):
    from picture_capture import layout_core_understanding as core

    marker = object()
    monkeypatch.setattr(core, "understand_layout_core",
                        lambda *args, **kwargs: marker)
    image = Image.new("RGB", (40, 30), "white")
    settings = AppSettings()
    settings.layout_mask_illustrations = False
    result = processing._understand_page_current(
        image, settings, page_index=1, page_sections=[],
        layout_only=True,
    )
    assert result is marker
