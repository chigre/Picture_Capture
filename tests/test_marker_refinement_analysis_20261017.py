"""Explicit marker refinement must prepare pixels/geometry without full Layout."""
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from picture_capture import marker_refinement_analysis as prep
from picture_capture.models import AppSettings


def _make_image():
    return Image.new("RGB", (110, 150), "white")


def test_refine_page_preparation_uses_denoise_mask_auto_policy_and_profile(monkeypatch, tmp_path):
    """The three switches must be resolved separately, not treated as OCR."""
    settings = AppSettings()
    settings.analysis_denoise_enabled = True
    settings.layout_mask_illustrations = True
    settings.layout_mask_illustrations_use_existing = False
    settings.ordinary_auto_layout = True
    seen = []
    monkeypatch.setattr(
        prep, "effective_page_settings",
        lambda current, size, index: (
            seen.append(("profile", index, size)) or current
        ),
    )
    monkeypatch.setattr(
        prep, "build_analysis_image",
        lambda image, effective: (seen.append("denoise") or image.copy()),
    )
    from picture_capture import layout_illustration_mask, dictionary_page_layout_policy
    def mask(image, effective, *, profile_page_index, **kwargs):
        seen.append(("mask", profile_page_index, kwargs))
        return image.copy(), object()
    monkeypatch.setattr(layout_illustration_mask, "mask_large_illustrations_for_layout", mask)
    def policy(image, effective, *, page_index):
        seen.append(("auto", page_index))
        return replace(effective, character_height=43), object(), {"character_height": 43}
    monkeypatch.setattr(dictionary_page_layout_policy, "resolve_page_layout_policy", policy)
    monkeypatch.setattr(
        prep, "page_template_analysis_image",
        lambda image, effective, index: (seen.append(("template", index)) or image.copy()),
    )
    image = _make_image()
    page = tmp_path / "scan.png"
    source, effective, analysis = prep.prepare_refinement_analysis(
        image, settings, 7, source_image_path=page,
    )
    try:
        assert seen == [
            ("profile", 7, image.size), "denoise",
            ("mask", 7, {}), ("auto", 7), ("template", 7),
        ]
        assert effective.character_height == 43
        assert source.size == analysis.size == image.size
        assert image.getpixel((0, 0)) == (255, 255, 255)
    finally:
        source.close()
        analysis.close()
        image.close()


def test_refine_page_preparation_disabled_stages_do_not_call_models(monkeypatch):
    settings = AppSettings()
    settings.analysis_denoise_enabled = False
    settings.layout_mask_illustrations = False
    settings.ordinary_auto_layout = False
    monkeypatch.setattr(prep, "effective_page_settings", lambda current, *_: current)
    from picture_capture import layout_illustration_mask, dictionary_page_layout_policy
    def forbidden(*_args, **_kwargs):
        raise AssertionError("disabled Layout stage must not be executed")
    monkeypatch.setattr(layout_illustration_mask, "mask_large_illustrations_for_layout", forbidden)
    monkeypatch.setattr(dictionary_page_layout_policy, "resolve_page_layout_policy", forbidden)
    monkeypatch.setattr(prep, "page_template_analysis_image", lambda image, *_: image.copy())
    image = _make_image()
    source, effective, analysis = prep.prepare_refinement_analysis(image, settings, 2)
    try:
        assert effective is settings
        assert source.size == analysis.size == image.size
    finally:
        image.close()
        source.close()
        analysis.close()


def test_refine_existing_ppp_mode_passes_path_without_redetection(monkeypatch, tmp_path):
    settings = AppSettings()
    settings.layout_mask_illustrations = True
    settings.layout_mask_illustrations_use_existing = True
    settings.ordinary_auto_layout = False
    monkeypatch.setattr(prep, "effective_page_settings", lambda current, *_: current)
    monkeypatch.setattr(prep, "build_analysis_image", lambda image, _: image.copy())
    monkeypatch.setattr(prep, "page_template_analysis_image", lambda image, *_: image.copy())
    from picture_capture import layout_illustration_mask
    page = tmp_path / "scan.png"
    seen = []
    def mask(image, effective, *, profile_page_index, **kwargs):
        seen.append(kwargs)
        return image.copy(), object()
    monkeypatch.setattr(layout_illustration_mask, "mask_large_illustrations_for_layout", mask)
    image = _make_image()
    with pytest.raises(ValueError, match="PPP"):
        prep.prepare_refinement_analysis(image, settings, 0)
    source, _, analysis = prep.prepare_refinement_analysis(
        image, settings, 0, source_image_path=page,
    )
    try:
        assert seen == [{"source_image_path": Path(page)}]
    finally:
        image.close()
        source.close()
        analysis.close()


def test_refine_processes_all_existing_entries_including_manual(monkeypatch, tmp_path):
    from dataclasses import dataclass
    from types import SimpleNamespace
    from picture_capture import processing_core, paddle_headwords

    @dataclass
    class Row:
        word: str
        x: int
        y: int
        manually_selected: bool = False

    class Geometry:
        top = 0
        column_widths = [80]
        transform = SimpleNamespace(canonical_image_for_analysis=lambda image: image)
        def source_to_canonical(self, x, y):
            return x, y
        def canonical_to_source(self, x, y):
            return x, y
        def x_at(self, col, y):
            return 5

    settings = AppSettings()
    geometry = Geometry()
    prepared = []
    def fake_prep(image, effective, index, *, source_image_path):
        prepared.append((index, str(source_image_path)))
        return image.copy(), effective, image.copy()
    monkeypatch.setattr(prep, "prepare_refinement_analysis", fake_prep)
    monkeypatch.setattr(processing_core, "derive_geometry", lambda *_: geometry)
    monkeypatch.setattr(processing_core, "column_index", lambda *_: 0)
    def move(gray, coarse_y, line_height, effective, **_kwargs):
        return coarse_y + 2, {"reason": "test"}
    monkeypatch.setitem(paddle_headwords.__dict__, "refine_separator_y", move)
    image = _make_image()
    page = tmp_path / "scan.png"
    old = [Row("manual", 9, 20, True), Row("auto", 9, 55, False)]
    updated, stats = processing_core.refine_existing_entries(
        image, old, settings, profile_page_index=4, source_image_path=page,
    )
    assert prepared == [(4, str(page))]
    assert [(row.word, row.y, row.manually_selected) for row in updated] == [
        ("manual", 22, True), ("auto", 57, False),
    ]
    assert [row.y for row in old] == [20, 55]
    assert stats["total"] == stats["moved"] == 2
    image.close()


def test_auto_policy_cache_reuses_only_same_image_and_settings(monkeypatch, tmp_path):
    settings = AppSettings()
    settings.analysis_denoise_enabled = False
    settings.layout_mask_illustrations = False
    settings.ordinary_auto_layout = True
    prep.clear_refinement_auto_policy_cache()
    monkeypatch.setattr(prep, "effective_page_settings", lambda current, *_: current)
    monkeypatch.setattr(prep, "page_template_analysis_image", lambda image, *_: image.copy())
    from picture_capture import dictionary_page_layout_policy
    calls = []
    def policy(image, effective, *, page_index):
        calls.append(page_index)
        return replace(effective, character_height=41), object(), {"character_height": 41}
    monkeypatch.setattr(dictionary_page_layout_policy, "resolve_page_layout_policy", policy)
    image = _make_image()
    page = tmp_path / "scan.png"
    try:
        for _ in range(2):
            source, effective, analysis = prep.prepare_refinement_analysis(
                image, settings, 6, source_image_path=page,
            )
            assert effective.character_height == 41
            source.close()
            analysis.close()
        assert calls == [6]  # Second press reuses physical parameters.
        image.putpixel((20, 20), (0, 0, 0))
        source, effective, analysis = prep.prepare_refinement_analysis(
            image, settings, 6, source_image_path=page,
        )
        source.close()
        analysis.close()
        assert calls == [6, 6]  # Changed original pixels invalidate the cache.
        settings.character_height += 3
        source, _, analysis = prep.prepare_refinement_analysis(
            image, settings, 6, source_image_path=page,
        )
        source.close()
        analysis.close()
        assert calls == [6, 6, 6]  # Changed Profile/settings invalidate it.
    finally:
        image.close()
        prep.clear_refinement_auto_policy_cache()


def test_auto_policy_cache_invalidates_on_existing_ppp_bytes(monkeypatch, tmp_path):
    from picture_capture import layout_illustration_mask, dictionary_page_layout_policy
    from picture_capture import project_storage

    settings = AppSettings()
    settings.analysis_denoise_enabled = False
    settings.layout_mask_illustrations = True
    settings.layout_mask_illustrations_use_existing = True
    settings.ordinary_auto_layout = True
    prep.clear_refinement_auto_policy_cache()
    monkeypatch.setattr(prep, "effective_page_settings", lambda current, *_: current)
    monkeypatch.setattr(prep, "page_template_analysis_image", lambda image, *_: image.copy())
    monkeypatch.setattr(
        layout_illustration_mask, "mask_large_illustrations_for_layout",
        lambda image, *_args, **_kwargs: (image.copy(), object()),
    )
    ppp = tmp_path / "page.ppp"
    ppp.write_bytes(b"old")
    monkeypatch.setattr(project_storage, "ppp_read_path_for_image", lambda _: ppp)
    calls = []
    def policy(image, effective, *, page_index):
        calls.append(page_index)
        return replace(effective), object(), {}
    monkeypatch.setattr(dictionary_page_layout_policy, "resolve_page_layout_policy", policy)
    image = _make_image()
    page = tmp_path / "page.png"
    try:
        for value in (b"old", b"old", b"new"):
            ppp.write_bytes(value)
            source, _, analysis = prep.prepare_refinement_analysis(
                image, settings, 2, source_image_path=page,
            )
            source.close()
            analysis.close()
        assert calls == [2, 2]
    finally:
        image.close()
        prep.clear_refinement_auto_policy_cache()


def test_auto_master_on_but_every_field_off_skips_detector(monkeypatch):
    from picture_capture.dictionary_page_layout_policy import AUTO_LAYOUT_FIELDS
    from picture_capture import dictionary_page_layout_policy

    settings = AppSettings()
    settings.analysis_denoise_enabled = False
    settings.layout_mask_illustrations = False
    settings.ordinary_auto_layout = True
    for _field, switch in AUTO_LAYOUT_FIELDS:
        setattr(settings, switch, False)

    monkeypatch.setattr(prep, "effective_page_settings", lambda current, *_: current)
    monkeypatch.setattr(prep, "page_template_analysis_image", lambda image, *_: image.copy())
    def forbidden(*_args, **_kwargs):
        raise AssertionError("No selected automatic fields: no detector allowed")
    monkeypatch.setattr(dictionary_page_layout_policy, "resolve_page_layout_policy", forbidden)
    image = _make_image()
    source, effective, analysis = prep.prepare_refinement_analysis(
        image, settings, 0, source_image_path=Path("dummy.png"),
    )
    assert not effective.manual_columns
    source.close()
    analysis.close()
    image.close()
