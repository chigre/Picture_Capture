from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from picture_capture.ocr_action_guard import _ineffective_lens_only_selection
from picture_capture.ordinary_action_runtime import _apply_quick_settings_for_ordinary
from picture_capture.settings_help_restore import install_settings_help_restore
from picture_capture.spawn_detection_runtime import (
    detect_entries_job_with_runtime,
    install_spawn_detection_runtime,
)
from picture_capture.ui_terminology import normalize_ui_text


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _FakeSettingsDialog:
    SETTING_HELP = {"ocr_engine": "old"}
    CHECK_HELP = {"paddle_use_paddleocr": "old"}

    def __init__(self):
        self.vars = {}


class _FakeAppModule:
    SettingsDialog = _FakeSettingsDialog


def _gui_composition_source() -> str:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "bootstrap"
        / "gui.py"
    ).read_text(encoding="utf-8")


def _worker_composition_source() -> str:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "bootstrap"
        / "worker.py"
    ).read_text(encoding="utf-8")


def test_settings_help_restore_installs_current_shared_ocr_wording_without_tk_root():
    install_settings_help_restore(_FakeAppModule)
    dialog = _FakeAppModule.SettingsDialog()
    assert dialog.vars == {}
    assert "共享 OCR 通道" in _FakeAppModule.SettingsDialog.SETTING_HELP["ocr_engine"]
    assert "共享 OCR 通道" in _FakeAppModule.SettingsDialog.CHECK_HELP["paddle_use_paddleocr"]


def test_gui_composition_installs_help_restore_after_compact_right_pane_builder():
    source = _gui_composition_source()
    compact = source.index("install_settings_parameter_help(app_module)")
    restore = source.index("install_settings_help_restore(app_module)")
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


def test_gui_composition_installs_ocr_guard_before_user_actions_run():
    source = _gui_composition_source()
    assert "install_ocr_action_guard" in source
    assert "install_ocr_action_guard(app_module)" in source


def test_shared_ocr_action_wording_no_longer_claims_marker_text_is_paddle_only():
    tooltip = normalize_ui_text("只对已有画线做局部 PaddleOCR 文字识别；不会改变画线")
    confirm = normalize_ui_text("将对 3 页逐条做局部 PaddleOCR。")
    assert "共享 OCR 通道" in tooltip
    assert "PaddleOCR 文字识别" not in tooltip
    assert "共享 OCR 通道" in confirm


def test_ordinary_quick_apply_allows_all_ocr_engines_off_and_restores_selection():
    app = _app_for_ocr_selection()
    # Model still contains the previously applied Paddle=True, while the user
    # has just unchecked all three visible OCR controls and immediately clicks
    # 【普通画线】. The visible controls must win.
    app.settings.paddle_use_paddleocr = True
    app.sync_calls = 0

    def legacy_apply(*, show_status=False):
        assert show_status is False
        paddle = bool(app.quick_bool_vars["paddle_use_paddleocr"].get())
        tesseract = bool(app.quick_bool_vars["paddle_compare_tesseract"].get())
        lens = bool(app.quick_bool_vars["paddle_enable_lens"].get())
        if not (paddle or tesseract or lens):
            raise ValueError("OCR引擎至少需要勾选一个。")
        app.settings.paddle_use_paddleocr = paddle
        app.settings.paddle_compare_tesseract = tesseract
        app.settings.paddle_enable_lens = lens
        return True

    def sync_quick_settings():
        app.sync_calls += 1
        app.quick_bool_vars["paddle_use_paddleocr"].set(
            app.settings.paddle_use_paddleocr
        )

    app.apply_quick_settings = legacy_apply
    app.sync_quick_settings = sync_quick_settings

    assert _apply_quick_settings_for_ordinary(app) is True
    assert app.settings.paddle_use_paddleocr is False
    assert app.quick_bool_vars["paddle_use_paddleocr"].get() is False
    assert app.sync_calls == 1


def test_ordinary_quick_apply_uses_normal_validator_when_ocr_is_selected():
    app = _app_for_ocr_selection(paddle=True)
    calls = []
    app.apply_quick_settings = lambda **kwargs: calls.append(kwargs) or True
    assert _apply_quick_settings_for_ordinary(app) is True
    assert calls == [{"show_status": False}]


def test_gui_composition_installs_ordinary_action_runtime():
    source = _gui_composition_source()
    assert "install_ordinary_action_runtime" in source
    assert "install_ordinary_action_runtime(app_module)" in source

    ordinary_source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "ordinary_action_runtime.py"
    ).read_text(encoding="utf-8")
    assert 'self.settings.detection_method = "left_edge"' in ordinary_source
    assert 'self._detect_pages(indices, method="left_edge", force_refresh=False)' in ordinary_source


def test_spawn_worker_is_top_level_pickleable_and_installed_before_app_import():
    assert detect_entries_job_with_runtime.__module__ == "picture_capture.spawn_detection_runtime"

    processing = SimpleNamespace()
    install_spawn_detection_runtime(processing)
    assert processing.detect_entries_job is detect_entries_job_with_runtime

    source = _gui_composition_source()
    install_at = source.index("install_spawn_detection_runtime(processing_module)")
    app_import_at = source.index("from .. import app as app_module")
    assert install_at < app_import_at


def test_spawn_worker_uses_explicit_worker_composition_and_sidecar_aware_pdic():
    root = Path(__file__).resolve().parents[1]
    worker = _worker_composition_source()
    job = (
        root / "src" / "picture_capture" / "spawn_detection_runtime.py"
    ).read_text(encoding="utf-8")

    assert "install_pdic_classification(formats)" in worker
    assert "install_processing_entry_classification(processing_module)" in worker
    assert "install_layout_row_recovery_runtime()" in worker
    assert "install_layout_column_drift_runtime()" in worker
    assert "install_layout_rows_persistence_runtime()" in worker

    assert "services = build_worker_services()" in job
    assert "formats.write_pdic(" in job
    assert "current = replace(settings)" in job
    # Composition ownership must not drift back into the pickleable job target.
    assert "install_pdic_classification(formats)" not in job
    assert "install_processing_entry_classification(processing_module)" not in job
    assert "install_layout_row_recovery_runtime()" not in job
    assert "install_layout_column_drift_runtime()" not in job
    assert "install_layout_rows_persistence_runtime()" not in job
