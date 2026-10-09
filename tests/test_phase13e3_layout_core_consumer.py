"""Phase 13E3: the Layout Core consumer is explicitly composed and cache-stable."""
from PIL import Image, ImageDraw

from picture_capture import dictionary_page_layout_policy as policy
from picture_capture import layout_core_understanding as core
from picture_capture.models import AppSettings


def _scan():
    image = Image.new("RGB", (280, 200), "white")
    draw = ImageDraw.Draw(image)
    for index in range(7):
        y = 16 + index * 22
        draw.rectangle((19, y, 31, y + 11), fill="black")
        draw.rectangle((48, y, 100, y + 11), fill="black")
    settings = AppSettings(
        columns=1, manual_x=15, column_width=180,
        start_y=7, character_height=14, ordinary_auto_layout=False,
    )
    return image, settings


def test_layout_core_bypasses_mutable_policy_and_preserves_cache_hit(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Layout Core should use explicitly composed policy")

    monkeypatch.setattr(policy, "resolve_page_layout_policy", forbidden)
    monkeypatch.setattr(policy, "infer_dictionary_page_layout", forbidden)
    original = core.infer_dictionary_page_layout
    calls = []

    def counted(*args, **kwargs):
        calls.append(kwargs.get("page_index"))
        return original(*args, **kwargs)

    monkeypatch.setattr(core, "infer_dictionary_page_layout", counted)
    image, settings = _scan()
    core._LAYOUT_CACHE.clear()
    try:
        first = core.understand_layout_core(image, settings, page_index=2)
        second = core.understand_layout_core(image, settings, page_index=2)
        assert second is first
        assert calls == [2]
        assert first.semantic_reliable is False
        assert first.layout.columns
        assert "layout_core" in first.layout.reason
    finally:
        core._LAYOUT_CACHE.clear()
        image.close()
