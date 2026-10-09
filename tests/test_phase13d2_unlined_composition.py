"""Phase 13D2: unlined QA uses only explicit physical composition at escalation."""
from types import SimpleNamespace

from PIL import Image

from picture_capture import layout_composition
from picture_capture import unlined_physical_rows_resolver as resolver
from picture_capture.models import AppSettings


def _layout():
    column = SimpleNamespace(lines=[
        SimpleNamespace(y0=i * 16, y1=i * 16 + 10) for i in range(6)
    ])
    return SimpleNamespace(columns=[column], ordinary_line_height=14.0)


def test_unlined_escalation_uses_explicit_physical_composition(monkeypatch, tmp_path):
    image = Image.new("RGB", (160, 140), "white")
    settings = AppSettings()
    page_path = tmp_path / "page.png"
    calls = []
    layout = _layout()

    monkeypatch.setattr(resolver, "load_layout_rows_cache", lambda *args, **kw: None)
    monkeypatch.setattr(resolver, "recover_physical_rows_fast", lambda *args, **kw: None)
    monkeypatch.setattr(resolver, "write_layout_rows_cache",
                        lambda *args, **kw: calls.append(("write", kw)))
    monkeypatch.setattr(
        layout_composition, "infer_composed_physical_page_layout",
        lambda image, settings, *, page_index=0:
            (calls.append(("composed", page_index)) or (layout, settings, {})),
    )

    actual, label = resolver.resolve_unlined_physical_rows(
        tmp_path, page_path, image, settings, page_index=3,
    )
    assert actual is layout
    assert label == "physical_detector"
    assert calls[0] == ("composed", 3)
    assert calls[1][0] == "write"


def test_unlined_cache_hit_skips_composed_detector(monkeypatch, tmp_path):
    layout = _layout()
    monkeypatch.setattr(resolver, "load_layout_rows_cache",
                        lambda *args, **kw: layout)
    monkeypatch.setattr(resolver, "recover_physical_rows_fast",
                        lambda *args, **kw: (_ for _ in ()).throw(
                            AssertionError("cache hit should return first")))
    got, reason = resolver.resolve_unlined_physical_rows(
        tmp_path, tmp_path / "page.png",
        Image.new("RGB", (160, 140)), AppSettings(),
    )
    assert got is layout
    assert reason == "cache"
