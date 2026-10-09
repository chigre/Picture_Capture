"""Phase 13E1: opt-in full understanding preserves legacy default entry point."""
from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture import layout_composition as composed
from picture_capture import page_understanding as understanding
from picture_capture.models import AppSettings


def _page():
    image = Image.new("RGB", (280, 200), "white")
    draw = ImageDraw.Draw(image)
    for i in range(7):
        top = 15 + i * 22
        draw.rectangle((20, top, 30, top + 11), fill="black")
        draw.rectangle((44, top, 96, top + 11), fill="black")
    settings = AppSettings(
        columns=1, manual_x=16, column_width=180,
        start_y=7, character_height=14, ordinary_auto_layout=False,
    )
    return image, settings


def test_composed_understanding_bypasses_mutable_legacy_entry_points(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("must use explicit composed page-layout boundary")

    monkeypatch.setattr(understanding, "understand_page", forbidden)
    monkeypatch.setattr(understanding, "infer_dictionary_page_layout", forbidden)
    image, settings = _page()
    result = composed.understand_composed_page(image, settings)
    assert result.layout.columns
    assert result.page_settings.manual_x == settings.manual_x
    assert result.role_model in ("cjk", "generic")


def test_composed_understanding_forwards_sections_and_finalizes_once(monkeypatch):
    call = []
    layout = object()
    marker = SimpleNamespace(layout=layout)

    def fake_raw(image, settings, **kwargs):
        call.append(("raw", kwargs))
        return marker

    monkeypatch.setattr(understanding, "_RAW_UNDERSTAND_PAGE", fake_raw)
    monkeypatch.setattr(composed, "normalize_layout_roles",
                        lambda obj: call.append(("finalize", obj)))
    sections = ["keep"]
    image, settings = _page()
    assert composed.understand_composed_page(
        image, settings, page_index=4, page_sections=sections,
    ) is marker
    assert call[0][0] == "raw"
    assert call[0][1]["page_index"] == 4
    assert call[0][1]["page_sections"] is sections
    assert call[0][1]["ops"] is not None
    assert callable(call[0][1]["layout_infer"])
    assert call[1] == ("finalize", layout)
    assert len(call) == 2
