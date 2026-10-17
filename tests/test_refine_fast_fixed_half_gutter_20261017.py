"""Fast explicit-Y half-gutter geometry and model-bypass regressions."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.marker_refinement_fixed_band import fixed_half_gutter_band
from picture_capture.models import AppSettings, Entry
from picture_capture import marker_refinement_analysis as prep


def _geometry(starts=(10, 100), widths=(70, 70)):
    return SimpleNamespace(
        column_widths=list(widths),
        x_at=lambda col, _y: starts[col],
    )


def test_fixed_band_includes_column_and_only_half_gutter_each_side():
    geo = _geometry()
    assert fixed_half_gutter_band(geo, 0, 30, 210, 70, 20) == (0, 90)
    assert fixed_half_gutter_band(geo, 1, 30, 210, 70, 20) == (90, 180)
    assert fixed_half_gutter_band(geo, 1, 30, 210, 70, 21) == (90, 181)


def test_neighbour_column_body_is_hard_clipping_limit():
    geo = _geometry(starts=(10, 100, 190), widths=(85, 85, 85))
    # The nominal +/-15 gutter would enter neighbouring bodies here.
    assert fixed_half_gutter_band(geo, 0, 30, 300, 85, 30) == (0, 100)
    assert fixed_half_gutter_band(geo, 1, 30, 300, 85, 30) == (95, 190)
    assert fixed_half_gutter_band(geo, 2, 30, 240, 85, 30) == (185, 240)


def test_invalid_page_geometry_fails_closed():
    geo = _geometry(starts=(10, 11), widths=(70, 70))
    with pytest.raises(ValueError, match="跨栏"):
        fixed_half_gutter_band(geo, 1, 30, 11, 70, 20)
    with pytest.raises(ValueError, match="序号"):
        fixed_half_gutter_band(geo, 2, 30, 100, 70, 20)


def test_fast_preparation_forces_temporary_whitefill_and_skips_auto_layout(
    monkeypatch, tmp_path,
):
    from picture_capture import dictionary_page_layout_policy as policy

    def forbidden(*_args, **_kwargs):
        raise AssertionError("fast Y must not call page layout detection")

    settings = AppSettings()
    settings.ordinary_auto_layout = True
    for _field, switch in policy.AUTO_LAYOUT_FIELDS:
        setattr(settings, switch, True)
    settings.layout_mask_illustrations = False
    settings.follow_column_deformation = True
    settings.paddle_separator_column_margin = 8

    monkeypatch.setattr(policy, "resolve_page_layout_policy", forbidden)
    monkeypatch.setattr(prep, "effective_page_settings", lambda current, size, i: current)
    stages = []

    def whitefill(image, current, page_index, *, source_image_path):
        stages.append(("whitefill", current.layout_mask_illustrations,
                       current.follow_column_deformation,
                       current.paddle_separator_column_margin))
        return image.copy()

    monkeypatch.setattr(prep, "whiten_illustrations_for_refinement", whitefill)
    monkeypatch.setattr(
        prep, "page_template_analysis_image",
        lambda image, current, index: image.copy(),
    )

    source_image = Image.new("RGB", (200, 150), "white")
    source, effective, analysis = prep.prepare_refinement_analysis(
        source_image, settings, 3, source_image_path=tmp_path / "scan.png",
        fixed_half_gutter=True,
    )
    try:
        assert stages == [("whitefill", True, False, 0)]
        assert effective.layout_mask_illustrations is True
        assert effective.follow_column_deformation is False
        assert effective.paddle_separator_column_margin == 0
        # This mode may never change the project settings or source pixels.
        assert settings.layout_mask_illustrations is False
        assert settings.follow_column_deformation is True
        assert settings.paddle_separator_column_margin == 8
        assert source_image.tobytes() == analysis.tobytes()
    finally:
        source.close()
        analysis.close()
        source_image.close()


def test_y_engine_checks_the_actual_fast_band_without_entering_next_column(monkeypatch):
    from picture_capture import processing_core
    from picture_capture.marker_refinement_top_edge import (
        refine_existing_marker_to_ink_top,
    )
    from picture_capture import marker_refinement_top_edge

    calls = []

    def capture(gray, y, h, settings, **kwargs):
        calls.append((kwargs["column_left"], kwargs["column_right"],
                      kwargs["anchor_x"], y))
        return y, {"reason": "verified_whole_column_blank"}

    monkeypatch.setattr(marker_refinement_top_edge,
                        "refine_existing_marker_to_ink_top", capture)
    settings = AppSettings()
    settings.columns, settings.column_width, settings.gutter = 2, 70, 20
    geo = processing_core.Geometry(
        [10, 100], [70, 70], 0, 120,
        [processing_core.ColumnPath([(0, 10), (120, 10)]),
         processing_core.ColumnPath([(0, 100), (120, 100)])],
        source_size=(210, 120),
    )
    image = Image.new("RGB", (210, 120), "white")
    entries = [Entry(word="first", x=10, y=40),
               Entry(word="next", x=100, y=60)]
    result, stats = processing_core._refine_existing_entries_with_geometry(
        entries, settings, image, geo,
        align_to_ink_top=True, fixed_half_gutter=True,
    )
    assert calls == [(0, 90, 10, 40), (90, 180, 100, 60)]
    assert [(x.word, x.x, x.y) for x in result] == [
        ("first", 10, 40), ("next", 100, 60),
    ]
    assert stats["moved"] == 0


def test_fast_button_and_spawn_worker_have_isolated_mode():
    from picture_capture.ui.compact_task_menus import ACTION_GROUPS
    from picture_capture.marker_refinement_parallel import refine_page_job
    import inspect

    assert any(("精修Y·固定半栏距", "refine_y_fixed_half_gutter") in group
               for group in ACTION_GROUPS if group)
    assert inspect.signature(refine_page_job).parameters["fixed_half_gutter"].default is False
    app = (Path(__file__).resolve().parents[1]
           / "src/picture_capture/app.py").read_text(encoding="utf-8")
    assert "return str(pages[index]), settings, index, fixed_half_gutter" in app
    assert "foreground_page_edit=True, allow_pdic_edits=True" in app
