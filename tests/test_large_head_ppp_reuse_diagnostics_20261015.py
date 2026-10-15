"""Regression: large-head diagnostics must respect Layout PPP-reuse semantics.

These tests exercise the *actual mask* and both diagnostic stages. The display
switch must remain read-only for PDIC and PPP, even with auto illustration
detection enabled.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.formats import write_ppp
from picture_capture.models import AppSettings, PolygonRegion
from picture_capture.project_storage import ppp_write_path_for_image
from picture_capture import large_head_visual_diagnostics as diagnostics
from picture_capture import large_head_visualization_ui as ui


def _stub_heavy_layout(monkeypatch, probe):
    import picture_capture.ordinary_unified_diagnostics as unified

    def fake_layout(candidate, _settings, **kwargs):
        probe.append(candidate.getpixel((120, 110)))
        return SimpleNamespace(layout=SimpleNamespace(columns=[]))

    monkeypatch.setattr(diagnostics, "understand_layout_core", fake_layout)
    monkeypatch.setattr(diagnostics, "_diagnostic_layout", lambda _layout: {
        "physical_rows": [], "columns": [], "ordinary_line_height": 25,
    })
    monkeypatch.setattr(unified, "compose_ordinary_evidence_report",
                        lambda *_args: {
                            "review_queue": [], "registry": [], "summary": {},
                        })


@pytest.mark.parametrize("method", ["left_edge", "paddleocr", "combined"])
def test_large_head_diagnostic_reuses_saved_ppp_without_writing(
    monkeypatch, tmp_path, method,
):
    page = tmp_path / "scan.png"
    image = Image.new("RGB", (400, 300), (80, 80, 80))
    ppp = ppp_write_path_for_image(page)
    polygon = PolygonRegion("MANUAL", [(90, 80), (180, 80), (180, 180), (90, 180)])
    write_ppp(ppp, [polygon], page.stem)
    original_ppp = ppp.read_bytes()
    settings = AppSettings(
        layout_mask_illustrations=True,
        layout_mask_illustrations_use_existing=True,
        detection_method=method,
    )
    seen = []
    _stub_heavy_layout(monkeypatch, seen)
    import picture_capture.processing as processing
    import picture_capture.processing_core as core

    def forbidden(*args, **kwargs):
        raise AssertionError("read-only diagnostic must not redetect/write PPP")

    monkeypatch.setattr(core, "detect_illustrations_to_ppp", forbidden)
    monkeypatch.setattr(core, "detect_illustration_regions_from_image", forbidden)
    forwarded = []

    def fake_entries(_image, _settings, **kwargs):
        forwarded.append(kwargs.get("source_image_path"))
        return [], None

    # Processing is a historical module proxy; using setattr here would
    # modify core.detect_entries and leak into unrelated tests on teardown.
    monkeypatch.setitem(processing.__dict__, "detect_entries", fake_entries)
    report = diagnostics.build_large_head_diagnostics(
        image, settings, source_image_path=page,
    )
    assert report["enabled"] is True
    assert seen == [(255, 255, 255)], "candidate Layout must see PPP-whitefilled region"
    assert forwarded == ([page] if method == "left_edge" else [])
    assert ppp.read_bytes() == original_ppp
    assert not (tmp_path / "scan.PDIC").exists()
    image.close()


def test_large_head_reuse_rejects_missing_path_or_ppp_with_actionable_reason(tmp_path):
    image = Image.new("RGB", (100, 140), "white")
    settings = AppSettings(
        layout_mask_illustrations=True,
        layout_mask_illustrations_use_existing=True,
    )
    with pytest.raises(ValueError, match="图片路径"):
        diagnostics.build_large_head_diagnostics(image, settings)
    with pytest.raises(FileNotFoundError, match="PPP"):
        diagnostics.build_large_head_diagnostics(
            image, settings, source_image_path=tmp_path / "missing.png",
        )
    image.close()


def test_auto_illustration_mode_does_not_write_ppp_from_diagnostic(monkeypatch, tmp_path):
    import picture_capture.processing_core as core
    import picture_capture.processing as processing
    page = tmp_path / "auto.png"
    image = Image.new("RGB", (400, 300), "white")
    settings = AppSettings(
        layout_mask_illustrations=True,
        layout_mask_illustrations_use_existing=False,
        detection_method="left_edge",
    )
    _stub_heavy_layout(monkeypatch, [])
    seen = []

    def forbid_write(*_args, **_kwargs):
        raise AssertionError("diagnostic tried to persist auto illustration PPP")

    monkeypatch.setattr(core, "detect_illustrations_to_ppp", forbid_write)
    monkeypatch.setattr(core, "detect_illustration_regions_from_image",
                        lambda *_args, **_kwargs: [])
    monkeypatch.setitem(processing.__dict__, "detect_entries",
                        lambda _img, _settings, **kwargs: (
                            seen.append(kwargs.get("source_image_path")) or [], None,
                        ))
    report = diagnostics.build_large_head_diagnostics(
        image, settings, source_image_path=page,
    )
    assert report["enabled"]
    assert seen == [None]
    assert not ppp_write_path_for_image(page).exists()
    image.close()


def test_display_entrypoint_passes_current_page_and_shows_real_error(monkeypatch, tmp_path):
    image = Image.new("RGB", (80, 100), "white")
    page = tmp_path / "scan.png"
    settings = AppSettings()
    received = []
    monkeypatch.setattr(ui, "_cache_key", lambda _app: ("fixed",))
    monkeypatch.setattr(
        diagnostics, "build_large_head_diagnostics",
        lambda _image, _settings, **kw: (
            received.append(kw) or {"candidates": [], "enabled": True}
        ),
    )
    app = SimpleNamespace(
        image=image, settings=settings, current_index=3, current_page=page,
        page_sections=[], _large_head_debug_snapshot=None,
    )
    ui.get_large_head_debug_snapshot(app)
    assert received == [{"page_index": 3, "page_sections": [],
                         "source_image_path": page}]

    class Flag:
        def __init__(self, value): self.value = value
        def get(self): return self.value
        def set(self, value): self.value = value

    class Canvas:
        def __init__(self): self.texts = []
        def delete(self, *_args): pass
        def create_text(self, *args, **kwargs):
            self.texts.append(kwargs.get("text", ""))
            return 1

    canvas = Canvas()
    app.canvas = canvas
    app.crop_preview_var = Flag(False)
    app._large_head_visualization_var = Flag(True)
    app.status_var = Flag("")
    monkeypatch.setattr(ui, "get_large_head_debug_snapshot",
                        lambda _app: (_ for _ in ()).throw(
                            ValueError("已启用复用但没有对应图片路径，无法确定 PPP")
                        ))
    ui.draw_large_head_debug_overlay(app)
    assert "PPP" in app.status_var.get()
    assert any("ValueError" in row and "PPP" in row for row in canvas.texts)
    image.close()
