"""Button preparation applies selected page-local Auto Layout geometry without OCR."""
from dataclasses import dataclass, replace
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


def test_explicit_refine_uses_selected_per_page_layout_without_ocr_or_denoise(
    monkeypatch, tmp_path,
):
    from picture_capture import dictionary_page_layout_policy, image_utils
    settings = AppSettings()
    settings.analysis_denoise_enabled = True
    settings.ordinary_auto_layout = True
    settings.ordinary_auto_start_y = True
    settings.ordinary_auto_manual_x = True
    settings.ordinary_auto_column_width = True
    settings.ordinary_auto_character_height = True
    settings.layout_mask_illustrations = False
    stages = []

    def physical_policy(image, current, *, page_index):
        stages.append(("physical", page_index, image.getpixel((22, 22))))
        resolved = replace(current)
        resolved.start_y = 16
        resolved.manual_x = 8
        resolved.column_width = 74
        resolved.character_height = 22
        return resolved, object(), {
            "start_y": 16, "manual_x": 8, "column_width": 74,
            "character_height": 22,
        }

    monkeypatch.setattr(
        dictionary_page_layout_policy, "resolve_page_layout_policy",
        physical_policy,
    )
    monkeypatch.setattr(image_utils, "build_analysis_image", _forbidden)
    monkeypatch.setattr(
        prep, "effective_page_settings",
        lambda current, size, index: (stages.append(("profile", size, index)) or current),
    )
    monkeypatch.setattr(
        prep, "page_template_analysis_image",
        lambda image, current, index: (
            stages.append(("template", index, current.column_width)) or image.copy()
        ),
    )
    original = _page()
    source, effective, prepared = prep.prepare_refinement_analysis(
        original, settings, 7, source_image_path=tmp_path / "page.png",
    )
    try:
        assert stages == [
            ("profile", original.size, 7),
            ("physical", 7, (0, 0, 0)),
            ("template", 7, 74),
        ]
        assert effective is not settings
        assert (effective.start_y, effective.manual_x,
                effective.column_width, effective.character_height) == (16, 8, 74, 22)
        assert effective.gutter == settings.gutter
        assert settings.column_width != 74
        assert source.tobytes() == prepared.tobytes() == original.tobytes()
    finally:
        source.close()
        prepared.close()
        original.close()


@pytest.mark.parametrize("master", [False, True])
def test_refine_skips_physical_detector_without_enabled_auto_fields(
    monkeypatch, master,
):
    from picture_capture import dictionary_page_layout_policy
    settings = AppSettings()
    settings.ordinary_auto_layout = master
    for _field, switch in dictionary_page_layout_policy.AUTO_LAYOUT_FIELDS:
        setattr(settings, switch, False)
    monkeypatch.setattr(
        dictionary_page_layout_policy, "resolve_page_layout_policy", _forbidden,
    )
    image = _page()
    source, effective, prepared = prep.prepare_refinement_analysis(
        image, settings, 1,
    )
    try:
        assert effective.column_width == settings.column_width
        assert source.tobytes() == prepared.tobytes()
    finally:
        source.close()
        prepared.close()
        image.close()


def test_auto_policy_only_updates_checked_fields_and_is_page_local(monkeypatch):
    from picture_capture import dictionary_page_layout_policy as policy
    settings = AppSettings()
    settings.ordinary_auto_layout = True
    for _field, switch in policy.AUTO_LAYOUT_FIELDS:
        setattr(settings, switch, False)
    settings.ordinary_auto_column_width = True
    settings.ordinary_auto_character_height = True
    settings.ordinary_auto_manual_x = True
    prior_gutter = settings.gutter
    prior_start = settings.start_y
    prior_columns = settings.columns
    observed = []

    def estimate(image, detector_settings):
        marker = image.getpixel((22, 22))[0]
        observed.append(marker)
        return SimpleNamespace(
            columns=8, start_y=91, manual_x=99,
            column_width=60 if marker == 0 else 80,
            gutter=30, character_height=22 if marker == 0 else 26,
            row_padding=15,
        )

    monkeypatch.setattr(policy, "detect_layout_parameters", estimate)
    monkeypatch.setattr(
        policy.base, "_analysis_page",
        lambda image, current, page_index: (image, image, None, current),
    )
    monkeypatch.setattr(
        policy, "register_page_manual_x",
        lambda canonical, current, estimation: SimpleNamespace(
            value=12 if canonical.getpixel((22, 22))[0] == 0 else 18,
        ),
    )
    first = _page()
    second = _page()
    second.putpixel((22, 22), (255, 255, 255))
    try:
        values = []
        for index, image in enumerate((first, second)):
            source, effective, prepared = prep.prepare_refinement_analysis(
                image, settings, index,
            )
            try:
                values.append((
                    effective.column_width,
                    effective.character_height,
                    effective.manual_x,
                    effective.gutter,
                    effective.start_y,
                    effective.columns,
                ))
            finally:
                source.close()
                prepared.close()
        assert observed == [0, 255]
        assert values == [
            (60, 22, 12, prior_gutter, prior_start, prior_columns),
            (80, 26, 18, prior_gutter, prior_start, prior_columns),
        ]
        assert (settings.gutter, settings.start_y, settings.columns) == (
            prior_gutter, prior_start, prior_columns,
        )
        assert settings.manual_x != values[1][2]
    finally:
        first.close()
        second.close()


def test_auto_whitefill_changes_analysis_only_never_writes_ppp(monkeypatch, tmp_path):
    from picture_capture import layout_illustration_mask, dictionary_page_layout_policy
    settings = AppSettings()
    settings.layout_mask_illustrations = True
    settings.layout_mask_illustrations_use_existing = False
    # This test isolates optional whitening, not per-page physical detection.
    settings.ordinary_auto_layout = False
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
    settings.ordinary_auto_layout = False
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
    settings.ordinary_auto_layout = False
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


def test_full_refine_pipeline_uses_per_page_column_width_and_line_height(
    monkeypatch, tmp_path,
):
    from picture_capture import (
        dictionary_page_layout_policy as policy,
        marker_refinement_top_edge, processing_core,
    )

    @dataclass
    class Row:
        word: str
        x: int
        y: int

    class Geometry:
        top = 0
        bottom = 150
        # Final-column geometry historically extends to page image edge.
        column_widths = [200]
        transform = SimpleNamespace(canonical_image_for_analysis=lambda image: image)
        def source_to_canonical(self, x, y):
            return x, y
        def canonical_to_source(self, x, y):
            return x, y
        def x_at(self, col, y):
            return 10

    settings = AppSettings()
    settings.ordinary_auto_layout = True
    for _field, switch in policy.AUTO_LAYOUT_FIELDS:
        setattr(settings, switch, False)
    settings.ordinary_auto_column_width = True
    settings.ordinary_auto_character_height = True
    effective_values = ((42, 20), (67, 30))
    seen = []

    def resolve(image, current, *, page_index):
        from dataclasses import replace
        page_settings = replace(current)
        page_settings.column_width, page_settings.character_height = (
            effective_values[page_index]
        )
        return page_settings, None, {
            "column_width": page_settings.column_width,
            "character_height": page_settings.character_height,
        }

    def refine(gray, coarse_y, line_height, current, *, column_left, column_right, **kw):
        seen.append((line_height, column_left, column_right, current.column_width))
        return coarse_y - 3, {"reason": "verified_whole_column_blank"}

    monkeypatch.setattr(policy, "resolve_page_layout_policy", resolve)
    monkeypatch.setattr(processing_core, "derive_geometry", lambda *_: Geometry())
    monkeypatch.setattr(processing_core, "column_index", lambda *_: 0)
    monkeypatch.setattr(
        marker_refinement_top_edge, "refine_existing_marker_to_ink_top", refine,
    )
    image = _page()
    entry = Row("entry", 15, 40)
    try:
        results = []
        for page_index in (0, 1):
            refined, stats = processing_core.refine_existing_entries(
                image, [entry], settings, profile_page_index=page_index,
                source_image_path=tmp_path / f"page{page_index}.png",
            )
            results.append((refined[0].y, stats["moved"]))
        assert results == [(37, 1), (37, 1)]
        assert seen == [(20, 10, 52, 42), (30, 10, 77, 67)]
        assert entry.y == 40
        assert settings.character_height not in (20, 30)
    finally:
        image.close()
