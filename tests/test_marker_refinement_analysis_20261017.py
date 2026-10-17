"""Button preparation is Profile geometry + optional illustration whitening only."""
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture import marker_refinement_analysis as prep
from picture_capture.models import AppSettings


def _page():
    image = Image.new("RGB", (110, 150), "white")
    image.putpixel((22, 22), (0, 0, 0))
    return image


def _forbidden(*_args, **_kwargs):
    raise AssertionError("Refine existing lines must not run heavy layout/OCR/denoise")


def test_explicit_refine_does_not_rerun_layout_or_denoise(monkeypatch, tmp_path):
    """Even when ordinary auto-layout/denoise are ON, button only adds masking."""
    from picture_capture import dictionary_page_layout_policy, image_utils
    settings = AppSettings()
    settings.analysis_denoise_enabled = True
    settings.ordinary_auto_layout = True
    settings.ordinary_auto_start_y = True
    settings.ordinary_auto_manual_x = True
    settings.layout_mask_illustrations = False
    monkeypatch.setattr(dictionary_page_layout_policy, "resolve_page_layout_policy", _forbidden)
    monkeypatch.setattr(image_utils, "build_analysis_image", _forbidden)
    stages = []
    monkeypatch.setattr(
        prep, "effective_page_settings",
        lambda current, size, index: (stages.append(("profile", size, index)) or current),
    )
    monkeypatch.setattr(
        prep, "page_template_analysis_image",
        lambda image, current, index: (stages.append(("template", index)) or image.copy()),
    )
    original = _page()
    source, effective, prepared = prep.prepare_refinement_analysis(
        original, settings, 7, source_image_path=tmp_path / "page.png",
    )
    try:
        assert stages == [("profile", original.size, 7), ("template", 7)]
        assert effective is settings
        assert source.tobytes() == prepared.tobytes() == original.tobytes()
    finally:
        source.close()
        prepared.close()
        original.close()


def test_auto_whitefill_changes_analysis_only_never_writes_ppp(monkeypatch, tmp_path):
    from picture_capture import layout_illustration_mask, dictionary_page_layout_policy
    settings = AppSettings()
    settings.layout_mask_illustrations = True
    settings.layout_mask_illustrations_use_existing = False
    settings.ordinary_auto_layout = True
    stages = []
    monkeypatch.setattr(dictionary_page_layout_policy, "resolve_page_layout_policy", _forbidden)
    monkeypatch.setattr(prep, "effective_page_settings", lambda current, *_: current)
    monkeypatch.setattr(prep, "page_template_analysis_image", lambda image, *_: image.copy())

    def mask(image, effective, *, profile_page_index, **kwargs):
        stages.append(("mask", profile_page_index, kwargs))
        filled = image.copy()
        filled.putpixel((22, 22), (255, 255, 255))
        return filled, object()

    monkeypatch.setattr(layout_illustration_mask, "mask_large_illustrations_for_layout", mask)
    original = _page()
    page = tmp_path / "scan.png"
    source, effective, prepared = prep.prepare_refinement_analysis(
        original, settings, 4, source_image_path=page,
    )
    try:
        assert stages == [("mask", 4, {})]
        assert prepared.getpixel((22, 22)) == (255, 255, 255)
        assert source.getpixel((22, 22)) == original.getpixel((22, 22)) == (0, 0, 0)
        assert not list(tmp_path.glob("*.ppp"))
    finally:
        prepared.close()
        source.close()
        original.close()


def test_existing_ppp_whitefill_receives_path_and_does_not_redetect(monkeypatch, tmp_path):
    from picture_capture import layout_illustration_mask
    settings = AppSettings()
    settings.layout_mask_illustrations = True
    settings.layout_mask_illustrations_use_existing = True
    monkeypatch.setattr(prep, "effective_page_settings", lambda current, *_: current)
    monkeypatch.setattr(prep, "page_template_analysis_image", lambda image, *_: image.copy())
    path = tmp_path / "scan.png"
    seen = []

    def mask(image, effective, *, profile_page_index, **kwargs):
        seen.append((profile_page_index, kwargs))
        return image.copy(), object()

    monkeypatch.setattr(layout_illustration_mask, "mask_large_illustrations_for_layout", mask)
    image = _page()
    with pytest.raises(ValueError, match="PPP"):
        prep.prepare_refinement_analysis(image, settings, 3)
    source, _, prepared = prep.prepare_refinement_analysis(
        image, settings, 3, source_image_path=path,
    )
    try:
        assert seen == [(3, {"source_image_path": Path(path)})]
    finally:
        source.close()
        prepared.close()
        image.close()


def test_missing_ppp_is_not_silently_replaced_by_auto_detection(tmp_path):
    settings = AppSettings()
    settings.layout_mask_illustrations = True
    settings.layout_mask_illustrations_use_existing = True
    image = _page()
    try:
        with pytest.raises(FileNotFoundError, match="PPP"):
            prep.prepare_refinement_analysis(
                image, settings, 0, source_image_path=tmp_path / "no_page.png",
            )
    finally:
        image.close()


def test_disabled_whitefill_does_not_call_detector(monkeypatch):
    from picture_capture import layout_illustration_mask
    settings = AppSettings()
    settings.layout_mask_illustrations = False
    monkeypatch.setattr(
        layout_illustration_mask, "mask_large_illustrations_for_layout", _forbidden,
    )
    image = _page()
    source, _, prepared = prep.prepare_refinement_analysis(image, settings, 1)
    try:
        assert source.tobytes() == prepared.tobytes() == image.tobytes()
    finally:
        prepared.close()
        source.close()
        image.close()


def test_refine_processes_all_existing_entries_including_manual(monkeypatch, tmp_path):
    from picture_capture import processing_core, marker_refinement_top_edge

    @dataclass
    class Row:
        word: str
        x: int
        y: int
        manually_selected: bool = False

    class Geometry:
        top = 0
        bottom = 150
        column_widths = [80]
        transform = SimpleNamespace(canonical_image_for_analysis=lambda image: image)
        def source_to_canonical(self, x, y):
            return x, y
        def canonical_to_source(self, x, y):
            return x, y
        def x_at(self, col, y):
            return 5

    prepared = []
    monkeypatch.setattr(
        prep, "prepare_refinement_analysis",
        lambda image, effective, index, *, source_image_path:
            (prepared.append((index, str(source_image_path))) or
             (image.copy(), effective, image.copy())),
    )
    monkeypatch.setattr(processing_core, "derive_geometry", lambda *_: Geometry())
    monkeypatch.setattr(processing_core, "column_index", lambda *_: 0)
    monkeypatch.setattr(
        marker_refinement_top_edge, "refine_existing_marker_to_ink_top",
        lambda gray, coarse_y, line_height, effective, **kwargs:
            (coarse_y + 2, {"reason": "verified_whole_column_blank"}),
    )
    image = _page()
    page = tmp_path / "scan.png"
    old = [Row("manual", 9, 20, True), Row("auto", 9, 55, False)]
    updated, stats = processing_core.refine_existing_entries(
        image, old, AppSettings(), profile_page_index=4, source_image_path=page,
    )
    try:
        assert prepared == [(4, str(page))]
        assert [(row.word, row.y, row.manually_selected) for row in updated] == [
            ("manual", 22, True), ("auto", 57, False),
        ]
        assert [row.y for row in old] == [20, 55]
        assert stats["total"] == stats["moved"] == 2
    finally:
        image.close()
