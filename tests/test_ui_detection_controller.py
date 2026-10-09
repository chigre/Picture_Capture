from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import picture_capture.ui.controllers.detection as detection_module
from picture_capture.models import AppSettings, Entry
from picture_capture.ui.controllers.detection import DetectionController


ROOT = Path(__file__).resolve().parents[1]


class _Var:
    def __init__(self, value) -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


class _App:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(detection_method="left_edge")
        self.ocr_refresh_var = _Var("reuse")
        self.current_index = 2
        self.project = SimpleNamespace(images=[object(), object(), object(), object()])
        self.guard_result = True
        self.apply_result = True
        self.selected_result = [1, 3]
        self.selected_error: Exception | None = None
        self.calls: list[tuple] = []
        self.errors: list[tuple[str, Exception]] = []

    def guard(self) -> bool:
        self.calls.append(("guard",))
        return self.guard_result

    def apply_quick_settings(self, *, show_status: bool) -> bool:
        self.calls.append(("apply_quick_settings", show_status))
        return self.apply_result

    def selected_page_indices(self) -> list[int]:
        self.calls.append(("selected_page_indices",))
        if self.selected_error is not None:
            raise self.selected_error
        return list(self.selected_result)

    def save_settings(self) -> None:
        self.calls.append(("save_settings",))

    def sync_quick_settings(self) -> None:
        self.calls.append(("sync_quick_settings",))

    def auto_detect_current(self, *, force_paddle_refresh: bool) -> None:
        self.calls.append(("auto_detect_current", force_paddle_refresh))

    def _detect_pages(self, indices, *, method: str, force_refresh: bool) -> None:
        self.calls.append(("detect_pages", list(indices), method, force_refresh))

    def show_error(self, title: str, exc: Exception) -> None:
        self.errors.append((title, exc))


def test_paddle_detect_current_preserves_setting_sync_save_and_current_page_call() -> None:
    app = _App()
    controller = DetectionController(app)

    controller.paddle_detect_current(force_refresh=True)

    assert app.settings.detection_method == "paddleocr"
    assert app.calls == [
        ("sync_quick_settings",),
        ("save_settings",),
        ("auto_detect_current", True),
    ]


def test_combined_action_preserves_validation_scope_method_and_refresh_semantics() -> None:
    app = _App()
    app.ocr_refresh_var = _Var("force")
    controller = DetectionController(app)

    controller.run_combined_draw_action()

    assert app.settings.detection_method == "combined"
    assert app.calls == [
        ("guard",),
        ("apply_quick_settings", False),
        ("selected_page_indices",),
        ("save_settings",),
        ("detect_pages", [1, 3], "combined", True),
    ]


def test_normal_action_preserves_ocr_independent_validation_scope_and_left_edge_routing() -> None:
    app = _App()
    controller = DetectionController(app)

    controller.run_normal_draw_action()

    assert app.settings.detection_method == "left_edge"
    assert app.calls == [
        ("guard",),
        ("apply_quick_settings", False),
        ("selected_page_indices",),
        ("save_settings",),
        ("detect_pages", [1, 3], "left_edge", False),
    ]


def test_ocr_action_preserves_reuse_refresh_semantics() -> None:
    app = _App()
    controller = DetectionController(app)

    controller.run_ocr_draw_action()

    assert app.settings.detection_method == "paddleocr"
    assert app.calls[-2:] == [
        ("save_settings",),
        ("detect_pages", [1, 3], "paddleocr", False),
    ]


def test_selected_scope_error_is_reported_without_mutating_detection_method() -> None:
    app = _App()
    problem = ValueError("bad range")
    app.selected_error = problem
    controller = DetectionController(app)

    controller.run_combined_draw_action()

    assert app.settings.detection_method == "left_edge"
    assert app.errors == [("页面范围无效", problem)]
    assert not any(call[0] in {"save_settings", "detect_pages"} for call in app.calls)


def test_action_validation_short_circuits_in_original_order() -> None:
    app = _App()
    controller = DetectionController(app)

    app.guard_result = False
    controller.run_ocr_draw_action()
    assert app.calls == [("guard",)]

    app.calls.clear()
    app.guard_result = True
    app.apply_result = False
    controller.run_combined_draw_action()
    assert app.calls == [("guard",), ("apply_quick_settings", False)]


def test_lens_checked_off_stops_ocr_actions_before_generic_guard() -> None:
    for method_name in ("run_ocr_draw_action", "run_combined_draw_action"):
        app = _App()
        app.quick_bool_vars = {
            "paddle_use_paddleocr": _Var(False),
            "paddle_compare_tesseract": _Var(False),
            "paddle_enable_lens": _Var(True),
        }
        app.lens_mode_var = _Var("① 关闭")
        controller = DetectionController(app)

        getattr(controller, method_name)()

        assert app.calls == []
        assert app.settings.detection_method == "left_edge"
        assert app.errors and app.errors[0][0] == "OCR 引擎配置无效"


def test_run_ocr_draw_preserves_current_and_all_scope_routing_without_save_settings() -> None:
    app = _App()
    controller = DetectionController(app)

    controller.run_ocr_draw("current", True)
    assert app.settings.detection_method == "paddleocr"
    assert app.calls[-1] == ("detect_pages", [2], "paddleocr", True)
    assert ("save_settings",) not in app.calls

    app.calls.clear()
    controller.run_ocr_draw("all", False)
    assert app.calls[-1] == ("detect_pages", [0, 1, 2, 3], "paddleocr", False)
    assert ("selected_page_indices",) not in app.calls


def test_batch_auto_detect_preserves_all_project_pages_current_method_and_refresh() -> None:
    app = _App()
    app.settings.detection_method = "combined"
    controller = DetectionController(app)

    controller.batch_auto_detect(force_paddle_refresh=True)

    assert app.calls == [
        ("detect_pages", [0, 1, 2, 3], "combined", True),
    ]
    assert ("save_settings",) not in app.calls
    assert ("selected_page_indices",) not in app.calls


def test_batch_auto_detect_missing_project_is_exact_no_op() -> None:
    app = _App()
    app.project = None
    controller = DetectionController(app)

    controller.batch_auto_detect(force_paddle_refresh=True)

    assert app.calls == []


class _CurrentDetectApp:
    def __init__(self, root: Path, page: Path) -> None:
        self.project = SimpleNamespace(root=root, images=[page])
        self.current_page = page
        self.current_index = 0
        self.settings = AppSettings(columns=1, detection_method="left_edge")
        self.page_sections = []
        self.entries = [Entry(word="old", x=5, y=10)]
        self._batch_active = False
        self.status_var = _Var("")
        self.calls: list[tuple] = []
        self.batch = None

    def guard(self) -> bool:
        self.calls.append(("guard",))
        return True

    def _guard_transformed_geometry(self, title: str) -> bool:
        self.calls.append(("guard_transformed_geometry", title))
        return True

    def _start_batch_task(self, title, items, worker, done, **kwargs):
        self.batch = (title, list(items), worker, done, kwargs)
        return True

    def _sort_entries_reading_order(self) -> None:
        self.calls.append(("sort_entries",))

    def _load_ocr_review_candidates(self) -> None:
        self.calls.append(("load_ocr_review_candidates",))

    def _refresh_page_quality_colors(self) -> None:
        self.calls.append(("refresh_page_quality_colors",))

    def _current_page_quality_text(self) -> str:
        return "quality"

    def redraw(self) -> None:
        self.calls.append(("redraw",))


def test_auto_detect_current_busy_guard_preserves_existing_status() -> None:
    app = SimpleNamespace(_batch_active=True, status_var=_Var(""))

    DetectionController(app).auto_detect_current()

    assert app.status_var.value == "后台画线任务运行中，暂不启动前台自动识别；可进行人工校对。"


def test_auto_detect_current_preserves_single_page_worker_and_done(tmp_path, monkeypatch) -> None:
    page = tmp_path / "001.png"
    Image.new("RGB", (80, 120), "white").save(page)
    app = _CurrentDetectApp(tmp_path, page)
    geometry = object()
    detected = [Entry(word="new", x=7, y=20)]
    calls: list[tuple] = []

    def fake_detect(image, settings, **kwargs):
        calls.append((image.size, settings.detection_method, kwargs))
        return detected, geometry

    monkeypatch.setattr(detection_module, "detect_entries", fake_detect)

    DetectionController(app).auto_detect_current(force_paddle_refresh=True)

    assert app.calls[:2] == [("guard",), ("guard_transformed_geometry", "自动画线")]
    assert app.batch is not None
    title, items, worker, done, kwargs = app.batch
    assert title == "当前页自动画线"
    assert items == [0]
    assert kwargs["item_label"](0) == "001.png"
    assert kwargs["refresh_page_quality"] is False

    result = worker(0, 1, 1)
    assert result == (detected, geometry, None)
    assert calls[0][0] == (80, 120)
    assert calls[0][1] == "left_edge"
    assert calls[0][2]["force_paddle_refresh"] is True
    assert calls[0][2]["profile_page_index"] == 0

    done(1, 1, False, [result], None)

    assert app.entries == detected
    assert ("sort_entries",) in app.calls
    assert ("redraw",) in app.calls
    assert app.status_var.value == "智能画线完成：检测到 1 个词条；可手动增删后保存"


def test_auto_detect_current_clicked_column_replaces_only_target_column(
    tmp_path, monkeypatch,
) -> None:
    page = tmp_path / "001.png"
    Image.new("RGB", (80, 120), "white").save(page)
    app = _CurrentDetectApp(tmp_path, page)
    app.entries = [
        Entry(word="keep", x=10, y=10),
        Entry(word="replace", x=60, y=20),
    ]
    geometry = object()
    detected = [
        Entry(word="ignored", x=12, y=30),
        Entry(word="fresh", x=65, y=40),
    ]
    monkeypatch.setattr(
        detection_module, "detect_entries", lambda *_args, **_kwargs: (detected, geometry),
    )
    monkeypatch.setattr(detection_module, "column_index_for_click", lambda _x, _g: 1)
    monkeypatch.setattr(
        detection_module, "column_index", lambda x, _g, _y: 0 if int(x) < 40 else 1,
    )

    DetectionController(app).auto_detect_current(clicked_x=70)
    _, _, worker, done, _ = app.batch
    result = worker(0, 1, 1)
    done(1, 1, False, [result], None)

    assert [(entry.word, entry.x) for entry in app.entries] == [
        ("keep", 10),
        ("fresh", 65),
    ]


def test_auto_detect_current_does_not_publish_to_different_page(tmp_path, monkeypatch) -> None:
    page = tmp_path / "001.png"
    other = tmp_path / "002.png"
    Image.new("RGB", (80, 120), "white").save(page)
    Image.new("RGB", (80, 120), "white").save(other)
    app = _CurrentDetectApp(tmp_path, page)
    original_entries = list(app.entries)
    result = ([Entry(word="new", x=7, y=20)], object(), None)
    monkeypatch.setattr(
        detection_module, "detect_entries", lambda *_args, **_kwargs: (result[0], result[1]),
    )

    DetectionController(app).auto_detect_current()
    _, _, _worker, done, _ = app.batch
    app.current_page = other
    done(1, 1, False, [result], None)

    assert app.entries == original_entries
    assert ("sort_entries",) not in app.calls
    assert ("redraw",) not in app.calls


def test_batch_ocr_preserves_filter_worker_persistence_and_done(tmp_path, monkeypatch) -> None:
    first = tmp_path / "001.png"
    second = tmp_path / "002.png"
    Image.new("RGB", (80, 120), "white").save(first)
    Image.new("RGB", (80, 120), "white").save(second)

    class BatchApp:
        def __init__(self) -> None:
            self.project = SimpleNamespace(root=tmp_path, images=[first, second])
            self.settings = AppSettings(columns=1)
            self._batch_active = False
            self.current_index = 1
            self.status_var = _Var("")
            self.calls: list[tuple] = []
            self.batch = None

        def _guard_transformed_geometry(self, title: str) -> bool:
            self.calls.append(("guard_transformed_geometry", title))
            return True

        def pages_tuple(self, index: int):
            return (str(index), "@", "@")

        def _start_batch_task(self, title, items, worker, done, **kwargs):
            self.batch = (title, list(items), worker, done, kwargs)
            return True

        def load_page(self, index: int) -> None:
            self.calls.append(("load_page", index))

    app = BatchApp()
    writes: list[tuple] = []
    exports: list[tuple] = []
    prompts: list[tuple] = []

    def fake_read_pdic(path):
        return [Entry(word="", x=4, y=10)] if Path(path).stem == "001" else []

    monkeypatch.setattr(detection_module, "read_pdic", fake_read_pdic)
    monkeypatch.setattr(
        detection_module.messagebox,
        "askyesno",
        lambda title, text, parent=None: prompts.append((title, text, parent)) or True,
    )
    monkeypatch.setattr(detection_module, "load_replace_rules", lambda _path: [])
    monkeypatch.setattr(
        detection_module,
        "effective_page_settings",
        lambda settings, _size, _index: settings,
    )
    monkeypatch.setattr(
        detection_module,
        "page_template_analysis_image",
        lambda image, _settings, _index: image,
    )
    monkeypatch.setattr(detection_module, "read_page_sections", lambda _page: [])
    monkeypatch.setattr(detection_module, "derive_geometry", lambda *_args: object())
    monkeypatch.setattr(
        detection_module,
        "sort_entries_reading_order",
        lambda entries, _geometry, _sections: entries,
    )
    monkeypatch.setattr(
        detection_module,
        "ocr_entries",
        lambda _image, _entries, _settings, _rules, **_kwargs: ["alpha"],
    )
    monkeypatch.setattr(detection_module, "qt_root", lambda _root: tmp_path / "qt")
    monkeypatch.setattr(
        detection_module,
        "export_ocred",
        lambda path, texts: exports.append((path, list(texts))),
    )
    monkeypatch.setattr(
        detection_module,
        "write_pdic",
        lambda path, entries, width, pages: writes.append(
            (path, [entry.word for entry in entries], width, pages)
        ),
    )

    DetectionController(app).batch_ocr()

    assert app.calls == [("guard_transformed_geometry", "批量 OCR")]
    assert len(prompts) == 1
    assert prompts[0][0] == "批量 OCR"
    assert prompts[0][2] is app
    assert app.batch is not None
    title, items, worker, done, kwargs = app.batch
    assert title == "批量 OCR"
    assert items == [0]
    assert kwargs["item_label"](0) == "001.png"

    assert worker(0, 1, 1) == 1
    assert exports == [(tmp_path / "qt" / "001.OCRed", ["alpha"])]
    assert writes and writes[0][1] == ["alpha"]
    assert writes[0][2] == 80
    assert writes[0][3] == ("0", "@", "@")

    done(1, 1, False, [1], None)

    assert ("load_page", 1) in app.calls
    assert app.status_var.value == "批量 OCR 完成：1 个词条"


def test_batch_ocr_no_eligible_pdic_sets_existing_status_without_starting_batch(
    tmp_path, monkeypatch,
) -> None:
    page = tmp_path / "001.png"
    Image.new("RGB", (40, 60), "white").save(page)
    app = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path, images=[page]),
        settings=AppSettings(),
        _batch_active=False,
        status_var=_Var(""),
        _guard_transformed_geometry=lambda _title: True,
    )
    monkeypatch.setattr(detection_module, "read_pdic", lambda _path: [])

    DetectionController(app).batch_ocr()

    assert app.status_var.value == "没有含 PDIC 词条的页面可执行批量 OCR"


def test_detection_controller_has_no_reverse_dependency_on_app_module() -> None:
    path = ROOT / "src/picture_capture/ui/controllers/detection.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_detection_controller_wiring_preserves_app_methods_and_static_guard_seam() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller = (
        ROOT / "src/picture_capture/ui/controllers/detection.py"
    ).read_text(encoding="utf-8")
    ocr_guard = (
        ROOT / "src/picture_capture/ocr_action_guard.py"
    ).read_text(encoding="utf-8")
    ordinary_runtime = (
        ROOT / "src/picture_capture/ordinary_quick_settings.py"
    ).read_text(encoding="utf-8")

    imports = app[: app.index("class PictureCaptureApp")]
    assert "DetectionController" in imports
    assert "self.detection_controller = DetectionController(self)" in app
    assert app.index("self.detection_controller = DetectionController(self)") < app.index("self._build_ui()")
    assert "def _detection_controller_for_call(" in app
    assert 'self.__dict__.get("detection_controller")' in app

    expected = {
        "auto_detect_current": "auto_detect_current",
        "run_normal_draw_action": "run_normal_draw_action",
        "paddle_detect_current": "paddle_detect_current",
        "run_combined_draw_action": "run_combined_draw_action",
        "run_ocr_draw_action": "run_ocr_draw_action",
        "batch_auto_detect": "batch_auto_detect",
        "batch_ocr": "batch_ocr",
        "run_ocr_draw": "run_ocr_draw",
    }
    for app_method, controller_method in expected.items():
        assert f"def {app_method}(" in app
        assert f"self._detection_controller_for_call().{controller_method}" in app
        assert f"def {controller_method}(" in controller

    # Phase 12L keeps the guard as a normal action-boundary preflight.
    assert "def guard_ocr_action_selection(" in ocr_guard
    assert "setattr(app_class, method_name, guarded)" not in ocr_guard
    assert controller.count("guard_ocr_action_selection(app)") >= 2

    # Phase 5A retires only the method monkey patch; the shared ordinary
    # quick-settings helper remains reusable by postproduction paths.
    assert "def install_ordinary_action_runtime" not in ordinary_runtime
    assert "def _apply_quick_settings_for_ordinary" in ordinary_runtime
    controller_tree = ast.parse(controller)
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "run_normal_draw_action"
        for node in ast.walk(controller_tree)
    )
