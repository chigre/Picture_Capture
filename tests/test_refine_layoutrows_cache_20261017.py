"""Validated LayoutRows shortcut used by normal single-page and batch Y refinement."""
from types import SimpleNamespace

from PIL import Image
from picture_capture.geometry.layout_transform import LayoutTransform
from picture_capture.layout_rows_cache import write_layout_rows_cache
from picture_capture.models import AppSettings
from picture_capture.refinement import analysis as prep


def _cached_layout(width, top):
    rows = [SimpleNamespace(
        y0=top + 3 + i * 10, y1=top + 9 + i * 10,
        first_x=2, anchor_x=2,
    ) for i in range(6)]
    return SimpleNamespace(
        transform=LayoutTransform("identity"),
        source_size=(180, 150),
        canonical_size=(180, 150),
        body_top=top,
        body_bottom=140,
        ordinary_line_height=12.0,
        columns=[SimpleNamespace(
            index=0, left=14, right=14 + width, lines=rows,
        )],
    )


def _settings():
    settings = AppSettings()
    settings.ordinary_auto_layout = True
    from picture_capture.design.layout_policy import AUTO_LAYOUT_FIELDS
    for _field, flag in AUTO_LAYOUT_FIELDS:
        setattr(settings, flag, False)
    settings.ordinary_auto_columns = True
    settings.ordinary_auto_manual_x = True
    settings.ordinary_auto_column_width = True
    settings.ordinary_auto_character_height = True
    settings.layout_mask_illustrations = False
    return settings


def test_two_pages_reuse_their_own_layoutrows_without_full_detection(tmp_path, monkeypatch):
    from picture_capture.design import layout_policy as policy
    monkeypatch.setattr(policy, "resolve_page_layout_policy",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("must use LayoutRows")
                        ))
    settings = _settings()
    for index, width in enumerate((75, 88)):
        page = tmp_path / f"scan_{index}.png"
        Image.new("RGB", (180, 150), "white").save(page)
        assert write_layout_rows_cache(
            tmp_path, page, index, settings, _cached_layout(width, 10 + index),
        ) is not None
        with Image.open(page) as image:
            source, effective, analysis = prep.prepare_refinement_analysis(
                image, settings, index, source_image_path=page,
            )
            try:
                assert effective.columns == 1
                assert effective.manual_x == 14
                assert effective.column_width == width
                assert effective.character_height == 12
            finally:
                source.close()
                analysis.close()


def test_unrelated_setting_change_still_reuses_physical_json(tmp_path, monkeypatch):
    from picture_capture.design import layout_policy as policy
    settings = _settings()
    page = tmp_path / "page.png"
    Image.new("RGB", (180, 150), "white").save(page)
    assert write_layout_rows_cache(
        tmp_path, page, 0, settings, _cached_layout(75, 10),
    ) is not None
    changed = _settings()
    changed.manual_x += 1  # project setting differs but JSON geometry remains authoritative
    seen = []

    def fake_policy(image, current, *, page_index):
        seen.append(page_index)
        return current, None, {}

    monkeypatch.setattr(policy, "resolve_page_layout_policy", fake_policy)
    with Image.open(page) as image:
        source, _, analysis = prep.prepare_refinement_analysis(
            image, changed, 0, source_image_path=page,
        )
        source.close()
        analysis.close()
    assert seen == []


def test_unrelated_row_padding_switch_reuses_needed_json_fields(tmp_path, monkeypatch):
    from picture_capture.design import layout_policy as policy
    from picture_capture import marker_refinement_parallel as batch
    settings = _settings()
    settings.ordinary_auto_row_padding = True
    page = tmp_path / "page.png"
    Image.new("RGB", (180, 150), "white").save(page)
    assert write_layout_rows_cache(
        tmp_path, page, 0, settings, _cached_layout(75, 10),
    ) is not None

    def forbidden(*_args, **_kwargs):
        raise AssertionError("row padding alone must not invalidate JSON geometry")

    monkeypatch.setattr(policy, "resolve_page_layout_policy", forbidden)
    assert batch._page_has_usable_refinement_json(page, 0, settings)
    with Image.open(page) as image:
        source, effective, analysis = prep.prepare_refinement_analysis(
            image, settings, 0, source_image_path=page,
        )
        try:
            assert (effective.column_width, effective.character_height) == (75, 12)
            assert prep.read_refinement_layout_source() == "layoutrows_cache"
        finally:
            source.close()
            analysis.close()


def test_row_padding_only_requires_no_layout_detector(tmp_path, monkeypatch):
    from picture_capture.design import layout_policy as policy
    from picture_capture import marker_refinement_parallel as batch
    settings = _settings()
    for _field, flag in policy.AUTO_LAYOUT_FIELDS:
        setattr(settings, flag, False)
    settings.ordinary_auto_row_padding = True
    assert not batch.refinement_uses_page_layout(settings)
    monkeypatch.setattr(
        policy, "resolve_page_layout_policy",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unnecessary GPU detector")
        ),
    )
    image = Image.new("RGB", (180, 150), "white")
    source, effective, analysis = prep.prepare_refinement_analysis(
        image, settings, 0, source_image_path=tmp_path / "page.png",
    )
    try:
        assert effective.row_padding == settings.row_padding
    finally:
        source.close()
        analysis.close()
        image.close()


def test_explicit_refine_switch_does_not_invalidate_physical_layoutrows(tmp_path, monkeypatch):
    """GUI forces the refinement-only switch, but cached page geometry is unchanged."""
    from picture_capture.design import layout_policy as policy
    from picture_capture.refinement import layoutrows as reuse
    original = _settings()
    original.paddle_refine_separator_y = False
    page = tmp_path / "scan.png"
    Image.new("RGB", (180, 150), "white").save(page)
    assert write_layout_rows_cache(
        tmp_path, page, 0, original, _cached_layout(75, 10),
    ) is not None
    enabled = _settings()
    enabled.paddle_refine_separator_y = True
    monkeypatch.setattr(
        policy, "resolve_page_layout_policy",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unexpected full GPU layout detection")
        ),
    )
    with Image.open(page) as image:
        source, effective, analysis = prep.prepare_refinement_analysis(
            image, enabled, 0, source_image_path=page,
        )
        try:
            assert effective.column_width == 75
            assert effective.manual_x == 14
            assert prep.read_refinement_layout_source() == "layoutrows_cache"
            assert reuse.cached_refinement_settings(
                page, (180, 150), enabled, 0,
            ) is not None
        finally:
            source.close()
            analysis.close()


def test_unrelated_setting_difference_does_not_invalidate_refinement_json(tmp_path):
    from picture_capture.refinement import layoutrows as reuse
    settings = _settings()
    settings.paddle_refine_separator_y = False
    page = tmp_path / "scan.png"
    Image.new("RGB", (180, 150), "white").save(page)
    assert write_layout_rows_cache(
        tmp_path, page, 0, settings, _cached_layout(75, 10),
    ) is not None
    changed = _settings()
    changed.paddle_refine_separator_y = True
    changed.manual_x += 1
    cached = reuse.cached_refinement_settings(page, (180, 150), changed, 0)
    assert cached is not None
    assert cached[1]["manual_x"] == 14
