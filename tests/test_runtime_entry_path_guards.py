from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from picture_capture.ocr_action_guard import _ineffective_lens_only_selection
from picture_capture.settings_help_restore import install_settings_help_restore
from picture_capture.spawn_detection_runtime import (
    detect_entries_job_with_runtime,
    install_spawn_detection_runtime,
)


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _FakeSettingsDialog:
    SETTING_HELP = {"ocr_engine": "old"}
    CHECK_HELP = {"paddle_use_paddleocr": "old"}

    def __init__(self):
        self.vars = {}


class _FakeAppModule:
    SettingsDialog = _FakeSettingsDialog


def test_settings_help_restore_installs_current_shared_ocr_wording_without_tk_root():
    install_settings_help_restore(_FakeAppModule)
    dialog = _FakeAppModule.SettingsDialog()
    assert dialog.vars == {}
    assert "共享 OCR 通道" in _FakeAppModule.SettingsDialog.SETTING_HELP["ocr_engine"]
    assert "共享 OCR 通道" in _FakeAppModule.SettingsDialog.CHECK_HELP["paddle_use_paddleocr"]


def test_launcher_installs_help_restore_after_compact_right_pane_builder():
    launcher = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "launcher.py"
    ).read_text(encoding="utf-8")
    compact = launcher.index("install_settings_parameter_help(app_module)")
    restore = launcher.index("install_settings_help_restore(app_module)")
    assert compact < restore


def test_settings_help_restore_binds_actual_textvariable_and_check_variable_widgets():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "settings_help_restore.py"
    ).read_text(encoding="utf-8")
    assert '_widget_variable(widget, "textvariable")' in source
    assert '_widget_variable(widget, "variable")' in source
    assert 'dialog._bind_help_widget(widget, callback)' in source


def _app_for_ocr_selection(*, paddle=False, tesseract=False, lens=False, lens_mode="off", rescue=False):
    return SimpleNamespace(
        quick_bool_vars={
            "paddle_use_paddleocr": _Var(paddle),
            "paddle_compare_tesseract": _Var(tesseract),
            "paddle_enable_lens": _Var(lens),
        },
        lens_mode_var=_Var(lens_mode),
        settings=SimpleNamespace(
            paddle_use_paddleocr=paddle,
            paddle_compare_tesseract=tesseract,
            paddle_enable_lens=lens,
            paddle_lens_mode=lens_mode,
            paddle_tesseract_rescue=rescue,
        ),
    )


def test_lens_checkbox_with_mode_off_is_not_a_runnable_lens_only_selection():
    app_module = SimpleNamespace(LENS_MODE_VALUES={"关闭": "off", "冲突时": "conflict"})
    invalid = _app_for_ocr_selection(lens=True, lens_mode="关闭")
    assert _ineffective_lens_only_selection(invalid, app_module) is True

    active_lens = _app_for_ocr_selection(lens=True, lens_mode="冲突时")
    assert _ineffective_lens_only_selection(active_lens, app_module) is False

    paddle_present = _app_for_ocr_selection(paddle=True, lens=True, lens_mode="关闭")
    assert _ineffective_lens_only_selection(paddle_present, app_module) is False

    tesseract_rescue_present = _app_for_ocr_selection(lens=True, lens_mode="关闭", rescue=True)
    assert _ineffective_lens_only_selection(tesseract_rescue_present, app_module) is False


def test_launcher_installs_ocr_guard_before_user_actions_run():
    launcher = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "launcher.py"
    ).read_text(encoding="utf-8")
    assert "from .ocr_action_guard import install_ocr_action_guard" in launcher
    assert "install_ocr_action_guard(app_module)" in launcher


def test_spawn_worker_is_top_level_pickleable_and_installed_before_app_import():
    assert detect_entries_job_with_runtime.__module__ == "picture_capture.spawn_detection_runtime"

    processing = SimpleNamespace()
    install_spawn_detection_runtime(processing)
    assert processing.detect_entries_job is detect_entries_job_with_runtime

    launcher = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "launcher.py"
    ).read_text(encoding="utf-8")
    install_at = launcher.index("install_spawn_detection_runtime(processing_module)")
    app_import_at = launcher.index("from . import app as app_module")
    assert install_at < app_import_at


def test_spawn_worker_bootstraps_classification_and_writes_sidecar_aware_pdic():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "spawn_detection_runtime.py"
    ).read_text(encoding="utf-8")
    assert "install_pdic_classification(formats)" in source
    assert "install_processing_entry_classification(processing_module)" in source
    assert "formats.write_pdic(" in source
    assert "current = replace(settings)" in source
