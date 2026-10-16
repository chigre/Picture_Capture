"""Linked column-relative crop width and page-ruler percent regressions."""
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

from PIL import Image

from picture_capture.models import AppSettings
import picture_capture.ui.crop_width_equivalence as width_link


def make_app(width=2000, column_width=800, crop_percent=10.0):
    root = tk.Tcl()
    settings = AppSettings(
        columns=2, manual_x=100, column_width=column_width,
        gutter=100, crop_width_percent=crop_percent,
    )
    app = SimpleNamespace(
        settings=settings,
        image=Image.new("RGB", (width, 120)),
        project=None,
        current_page=None,
        current_index=0,
        quick_vars={
            "crop_width_percent": tk.StringVar(master=root, value=str(crop_percent)),
            "column_width": tk.StringVar(master=root, value=str(column_width * 100 / width)),
            "manual_x": tk.StringVar(master=root, value=str(100 * 100 / width)),
            "columns": tk.StringVar(master=root, value="2"),
            "gutter": tk.StringVar(master=root, value=str(100 * 100 / width)),
        },
    )
    return root, app


def test_bidirectional_math_uses_whole_page_denominator():
    assert width_link.column_to_page_percent(5, 2000, 800) == 2
    assert width_link.page_to_column_percent(2, 2000, 800) == 5
    assert width_link.column_to_page_percent(100, 2000, 800) == 40


def test_editing_either_field_updates_the_other_not_display_marker_ratio():
    root, app = make_app()
    link = width_link.CropWidthEquivalence(app)
    assert link.page_percent_var.get() == "4"
    app.quick_vars["crop_width_percent"].set("5")
    assert link.page_percent_var.get() == "2"
    link.page_percent_var.set("3")
    assert float(app.quick_vars["crop_width_percent"].get()) == 7.5
    assert app.settings.crop_width_percent == 10  # Only the primary autosave owns persistence.
    app.image.close()


def test_page_geometry_and_column_width_changes_recompute_secondary_field():
    _root, app = make_app()
    link = width_link.CropWidthEquivalence(app)
    assert link.page_percent_var.get() == "4"
    app.quick_vars["column_width"].set("50")  # Unsaved primary quick-geometry edit.
    assert link.page_percent_var.get() == "5"
    assert app.quick_vars["crop_width_percent"].get() == "10.0"
    app.image.close()


def test_page_change_recomputes_from_current_image_when_settings_sync():
    _root, app = make_app()
    link = width_link.CropWidthEquivalence(app)
    assert link.page_percent_var.get() == "4"
    app.image.close()
    app.image = Image.new("RGB", (4000, 120))
    # load_page -> sync_quick_settings() reassigns the primary and geometry vars.
    app.quick_vars["column_width"].set("20")
    app.quick_vars["manual_x"].set("2.5")
    app.quick_vars["crop_width_percent"].set("10")
    assert link.page_percent_var.get() == "2"
    app.image.close()


def test_invalid_or_out_of_range_page_percent_never_changes_primary():
    _root, app = make_app()
    link = width_link.CropWidthEquivalence(app)
    link.page_percent_var.set("80")  # First column covers only 40% of the page.
    assert app.quick_vars["crop_width_percent"].get() == "10.0"
    link.commit_page()
    assert link.page_percent_var.get() == "4"
    link.page_percent_var.set("")
    link.commit_page()
    assert link.page_percent_var.get() == "4"
    link.page_percent_var.set("0.1")  # Less than minimum 1% of the column.
    link.commit_page()
    assert link.page_percent_var.get() == "4"
    app.image.close()


def test_current_page_layout_cache_overrides_profile_reference(monkeypatch, tmp_path):
    _root, app = make_app()
    app.project = SimpleNamespace(root=tmp_path)
    app.current_page = Path(tmp_path / "001.png")
    monkeypatch.setattr(
        width_link, "load_layout_rows_cache",
        lambda *args, **kwargs: SimpleNamespace(
            columns=[SimpleNamespace(index=0, left=100, right=960)]
        ),
    )
    link = width_link.CropWidthEquivalence(app)
    assert link.page_percent_var.get() == "4.3"
    app.quick_vars["column_width"].set("50")
    # A new (unsaved) geometry edit must not use stale cached column width.
    assert link.page_percent_var.get() == "5"
    app.image.close()


def test_no_page_then_page_open_and_first_column_clip():
    _root, app = make_app(width=2000, column_width=800)
    app.image.close()
    app.image = None
    link = width_link.CropWidthEquivalence(app)
    assert link.page_percent_var.get() == "—"
    app.image = Image.new("RGB", (2000, 120))
    app.quick_vars["crop_width_percent"].set("10")
    assert link.page_percent_var.get() == "4"
    app.settings.manual_x = 1900
    app.quick_vars["manual_x"].set("95")
    assert link.page_percent_var.get() == "0.5"
    app.image.close()


def test_link_is_ui_only_not_a_new_model_or_export_argument():
    source = (
        Path(__file__).resolve().parents[1]
        / "src/picture_capture/ui/compact_task_menus.py"
    ).read_text(encoding="utf-8")
    assert 'app._crop_width_equivalence = CropWidthEquivalence(app)' in source
    assert '"相当于整页宽(%):"' in source
    assert 'app.quick_vars["crop_width_percent"]' in source
    assert "page_width_entry" in source
    assert source.index('"切图宽度(%)"') < source.index('"相当于整页宽(%):"')
