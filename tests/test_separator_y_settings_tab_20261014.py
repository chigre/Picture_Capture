from picture_capture.models import AppSettings
from picture_capture.ui.settings import schema


def test_new_project_uses_full_width_refinement():
    assert AppSettings().paddle_separator_roi_width_ratio == 100.0


def test_old_settings_with_implicit_width_keep_old_default(tmp_path):
    import json
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"columns": 2}), encoding="utf-8")
    assert AppSettings.from_json(path).paddle_separator_roi_width_ratio == 60.0
    path.write_text(json.dumps({"paddle_separator_roi_width_ratio": 78.0}), encoding="utf-8")
    assert AppSettings.from_json(path).paddle_separator_roi_width_ratio == 78.0


def test_y_settings_have_only_one_owner():
    five = {
        "paddle_separator_search_ratio",
        "paddle_separator_band_radius",
        "paddle_separator_safety_px",
        "paddle_separator_roi_width_ratio",
        "paddle_separator_column_margin",
        "separator_y_max_shift_ratio",
        "separator_y_ink_safe_max_fraction",
        "separator_y_ink_safe_ink_threshold",
        "separator_y_ink_safe_existing_ink_ratio",
        "separator_y_ink_safe_gap_ink_ratio",
    }
    assert set(schema.SEPARATOR_Y_FIELDS) == five
    assert not five.intersection(schema.OCR_COMMON_FIELDS)
    assert not five.intersection(schema.OCR_ADVANCED_FIELDS)
    fields = {name for _label, name in schema.SEPARATOR_Y_CHECKS}
    assert fields == {"paddle_refine_separator_y", "separator_y_ink_safe_gap"}
    assert "paddle_refine_separator_y" not in {name for _, name in schema.OCR_COMMON_CHECKS}
    assert "paddle_refine_separator_y" not in {name for _, name in schema.NORMAL_CHECKS}
