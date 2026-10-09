from __future__ import annotations

from contextlib import contextmanager
import inspect
from pathlib import Path
import pickle
from types import SimpleNamespace

from PIL import Image

from picture_capture import processing as processing_module
from picture_capture.models import AppSettings
from picture_capture.ocr_action_guard import (
    _ineffective_lens_only_selection,
    guard_ocr_action_selection,
)
from picture_capture.ordinary_quick_settings import _apply_quick_settings_for_ordinary
from picture_capture.settings_help_restore import install_settings_help_restore
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


def test_static_ocr_preflight_reports_invalid_selection_before_action_runs():
    app_module = SimpleNamespace(LENS_MODE_VALUES={"关闭": "off"})
    invalid = _app_for_ocr_selection(lens=True, lens_mode="关闭")
    errors = []
    invalid.show_error = lambda title, exc: errors.append((title, exc))

    assert guard_ocr_action_selection(invalid, app_module) is False
    assert errors and errors[0][0] == "OCR 引擎配置无效"


def test_gui_composition_no_longer_installs_ocr_guard_and_actions_call_it_statically():
    source = _gui_composition_source()
    assert "install_ocr_action_guard" not in source

    root = Path(__file__).resolve().parents[1]
    controller = (
        root / "src" / "picture_capture" / "ui" / "controllers" / "detection.py"
    ).read_text(encoding="utf-8")
    app = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")

    assert controller.count("guard_ocr_action_selection(app)") >= 2
    start = app.index("    def ocr_ordinary_lines_text_selected_scope")
    end = app.index("\n    def ", start + 8)
    existing_marker_action = app[start:end]
    assert "guard_ocr_action_selection(self)" in existing_marker_action
    assert existing_marker_action.index("guard_ocr_action_selection(self)") < (
        existing_marker_action.index("self.guard()")
    )


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


def test_gui_composition_no_longer_installs_ordinary_action_runtime():
    source = _gui_composition_source()
    assert "install_ordinary_action_runtime" not in source

    ordinary_helper_source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "ordinary_quick_settings.py"
    ).read_text(encoding="utf-8")
    assert "def install_ordinary_action_runtime" not in ordinary_helper_source
    assert "def _apply_quick_settings_for_ordinary" in ordinary_helper_source

    controller_source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "ui"
        / "controllers"
        / "detection.py"
    ).read_text(encoding="utf-8")
    assert 'app.settings.detection_method = "left_edge"' in controller_source
    assert 'app._detect_pages(indices, method="left_edge", force_refresh=False)' in controller_source


def test_spawn_worker_is_static_top_level_pickleable_without_gui_mutation():
    job = processing_module.detect_entries_job
    assert job.__module__ == "picture_capture.processing"
    payload = pickle.dumps(job)
    assert b"picture_capture.processing" in payload

    source = _gui_composition_source()
    assert "install_spawn_detection_runtime" not in source
    assert "install_processing_entry_classification" not in source
    assert "entry_classification_runtime" not in source
    assert "from .. import app as app_module" in source


def test_static_spawn_worker_preserves_worker_services_contract(tmp_path, monkeypatch):
    from picture_capture.bootstrap import worker as worker_bootstrap

    page = tmp_path / "000001.png"
    Image.new("RGB", (40, 50), "white").save(page)
    pdic = tmp_path / "000001.pdic"
    settings = AppSettings(detection_method="combined")
    events: list[tuple] = []

    @contextmanager
    def capture_layout_rows(root, page_path, page_index, original_settings):
        events.append(("capture_enter", root, page_path, page_index, original_settings))
        yield
        events.append(("capture_exit",))

    fake_core = SimpleNamespace(
        normalize_page_rgb=lambda opened: opened.convert("RGB"),
        read_page_sections=lambda page_path: ["section"],
        pdic_path_for_image=lambda page_path: pdic,
    )

    def detect_entries(image, current, *, profile_page_index, page_sections):
        events.append(
            (
                "detect",
                current,
                current.detection_method,
                profile_page_index,
                page_sections,
                image.size,
            )
        )
        return [SimpleNamespace(word="entry")], SimpleNamespace()

    fake_processing = SimpleNamespace(_core=fake_core, detect_entries=detect_entries)
    fake_formats = SimpleNamespace(
        write_pdic=lambda path, entries, width, pages: events.append(
            ("write", path, len(entries), width, pages)
        )
    )
    fake_services = SimpleNamespace(
        processing=fake_processing,
        formats=fake_formats,
        capture_layout_rows=capture_layout_rows,
        save_automatic_baseline=lambda path, entries, width, pages: events.append(
            ("baseline", path, len(entries), width, pages)
        ),
    )
    monkeypatch.setattr(
        worker_bootstrap,
        "build_worker_services",
        lambda: fake_services,
    )

    count = processing_module.detect_entries_job(
        str(page),
        settings,
        ("p1", "p2", "p3"),
        7,
    )

    assert count == 1
    assert settings.detection_method == "combined"
    assert events[0][:4] == ("capture_enter", tmp_path, page, 7)
    assert events[0][4] is settings
    assert events[1][0] == "detect"
    assert events[1][1] is not settings
    assert events[1][2:] == ("left_edge", 7, ["section"], (40, 50))
    assert events[2] == ("capture_exit",)
    assert events[3] == ("baseline", pdic, 1, 40, ("p1", "p2", "p3"))
    assert events[4] == ("write", pdic, 1, 40, ("p1", "p2", "p3"))


def test_spawn_worker_uses_core_owned_sidecar_pdic_composition():
    root = Path(__file__).resolve().parents[1]
    worker = _worker_composition_source()
    job = inspect.getsource(processing_module.detect_entries_job)

    assert "core_services = build_core_services()" in worker
    assert "install_pdic_classification(formats)" not in worker
    assert "install_processing_entry_classification" not in worker
    assert "entry_classification_runtime" not in worker
    assert "install_layout_row_recovery_runtime" not in worker
    assert "install_layout_column_drift_runtime()" not in worker
    policy = (
        root / "src" / "picture_capture" / "dictionary_page_layout_policy.py"
    ).read_text(encoding="utf-8")
    assert "finalize_layout_column_drift(" in policy
    assert "install_layout_rows_persistence_runtime()" not in worker

    assert "from .bootstrap.worker import build_worker_services" in job
    assert "services = build_worker_services()" in job
    assert "with services.capture_layout_rows(" in job
    assert "formats.write_pdic(" in job
    assert "services.save_automatic_baseline(" in job
    assert "current = replace(settings)" in job
    assert 'current.detection_method = "left_edge"' in job
    # Composition ownership must not drift back into the pickleable job target.
    assert "install_pdic_classification(formats)" not in job
    assert "install_processing_entry_classification(processing_module)" not in job
    assert "install_layout_row_recovery_runtime()" not in job
    assert "install_layout_column_drift_runtime()" not in job
    assert "install_layout_rows_persistence_runtime()" not in job
