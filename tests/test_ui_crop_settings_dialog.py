from __future__ import annotations

from pathlib import Path

from picture_capture.app import (
    CROP_SETTINGS_VERSION as AppCropSettingsVersion,
    CropSettingsDialog as AppCropSettingsDialog,
    _normalize_crop_settings_payload as app_normalize_crop_settings_payload,
)
from picture_capture.crop.settings import (
    CROP_SETTINGS_VERSION,
    SINGLE_LINE_MERGE_KEY,
    normalize_crop_settings_payload,
)
from picture_capture.models import AppSettings
from picture_capture.ui.dialogs.crop_settings import CropSettingsDialog


ROOT = Path(__file__).resolve().parents[1]


def test_crop_settings_dialog_has_stable_direct_import_and_app_compatibility_alias() -> None:
    assert AppCropSettingsDialog is CropSettingsDialog
    assert CropSettingsDialog.__module__ == "picture_capture.ui.dialogs.crop_settings"
    assert CropSettingsDialog.CONFIG_NAME == "_CropSettings.json"


def test_crop_settings_schema_has_stable_app_compatibility_alias() -> None:
    assert AppCropSettingsVersion == CROP_SETTINGS_VERSION == 7
    assert app_normalize_crop_settings_payload is normalize_crop_settings_payload


def test_crop_settings_schema_remains_ui_free_and_preserves_coordinate_contract() -> None:
    source = (ROOT / "src" / "picture_capture" / "crop" / "settings.py").read_text(
        encoding="utf-8"
    )
    assert "tkinter" not in source
    assert "picture_capture.app" not in source

    settings = AppSettings(
        start_y=31,
        bottom_y=920,
        crop_to_bottom_y=True,
        crop_parallel_workers=3,
    )
    payload = normalize_crop_settings_payload(None, settings)
    assert payload["version"] == 7
    assert payload["coordinate_space"] == "source_image_pixels"
    assert payload["general_top_y"] == 31
    assert payload["general_bottom_y"] == 920
    assert payload["parallel_workers"] == 3
    assert payload[SINGLE_LINE_MERGE_KEY] is False

    raw = dict(payload)
    raw[SINGLE_LINE_MERGE_KEY] = True
    normalized = normalize_crop_settings_payload(raw, settings)
    assert normalized[SINGLE_LINE_MERGE_KEY] is True


def test_crop_settings_dialog_module_does_not_import_app() -> None:
    source = (
        ROOT / "src" / "picture_capture" / "ui" / "dialogs" / "crop_settings.py"
    ).read_text(encoding="utf-8")
    app_source = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")

    assert "from ...app" not in source
    assert "import picture_capture.app" not in source
    assert "class CropSettingsDialog" in source
    assert "class CropSettingsDialog" not in app_source
    assert "from .ui.dialogs.crop_settings import CropSettingsDialog" in app_source
