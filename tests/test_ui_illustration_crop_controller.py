from __future__ import annotations

from pathlib import Path

import pytest

import picture_capture.ui.controllers.illustration as illustration_module
from picture_capture.ui.controllers.illustration import IllustrationController


ROOT = Path(__file__).resolve().parents[1]


class _StatusVar:
    def __init__(self) -> None:
        self.values: list[str] = []

    def set(self, value: str) -> None:
        self.values.append(value)


class _CropApp:
    def __init__(self) -> None:
        self._batch_active = False
        self.project = object()
        self.current_page = Path("/pages/page001.png")
        self.image = object()
        self.polygons = ["manual-polygon"]
        self.status_var = _StatusVar()
        self.indices = [0, 2]
        self.range_error: Exception | None = None
        self.crop_config = {"marker": 7}
        self.events: list[tuple] = []
        self.errors: list[tuple[str, Exception]] = []
        self.started: tuple[list[int], dict] | None = None

    def selected_page_indices(self) -> list[int]:
        self.events.append(("selected_page_indices",))
        if self.range_error is not None:
            raise self.range_error
        return list(self.indices)

    def show_error(self, title: str, exc: Exception) -> None:
        self.events.append(("show_error", title, exc))
        self.errors.append((title, exc))

    def _sync_polygon_label_texts(self) -> None:
        self.events.append(("sync_polygon_label_texts",))

    def _ppp_write_path(self, page: Path) -> Path:
        self.events.append(("ppp_write_path", page))
        return Path("/custom-ppp") / f"{page.stem}.ppp"

    def _load_crop_settings(self) -> dict:
        self.events.append(("load_crop_settings",))
        return self.crop_config

    def _start_illustration_crop(self, indices: list[int], config: dict) -> None:
        self.events.append(("start_illustration_crop", list(indices), config))
        self.started = (list(indices), config)


def _stub_info(monkeypatch):
    infos: list[tuple] = []

    def showinfo(title, text, *, parent=None):
        infos.append((title, text, parent))

    monkeypatch.setattr(illustration_module.messagebox, "showinfo", showinfo)
    return infos


def test_crop_entry_batch_active_short_circuits_before_project_checks(monkeypatch) -> None:
    app = _CropApp()
    app._batch_active = True
    infos = _stub_info(monkeypatch)

    IllustrationController(app).split_illustrations_selected_scope()

    assert app.status_var.values == ["已有批量任务正在运行，请结束后再执行插图切图。"]
    assert app.events == []
    assert app.started is None
    assert infos == []


@pytest.mark.parametrize("missing", ["project", "current_page", "image"])
def test_crop_entry_missing_foreground_state_preserves_original_dialog(monkeypatch, missing: str) -> None:
    app = _CropApp()
    setattr(app, missing, None)
    infos = _stub_info(monkeypatch)

    IllustrationController(app).split_illustrations_selected_scope()

    assert infos == [("尚未打开", "请先打开包含扫描图片的项目目录。", app)]
    assert app.events == []
    assert app.started is None


def test_crop_entry_invalid_and_empty_ranges_preserve_original_behavior(monkeypatch) -> None:
    app = _CropApp()
    problem = ValueError("bad range")
    app.range_error = problem
    infos = _stub_info(monkeypatch)

    IllustrationController(app).split_illustrations_selected_scope()

    assert app.events == [
        ("selected_page_indices",),
        ("show_error", "页面范围无效", problem),
    ]
    assert app.errors == [("页面范围无效", problem)]
    assert app.started is None
    assert infos == []

    app = _CropApp()
    app.indices = []
    infos = _stub_info(monkeypatch)

    IllustrationController(app).split_illustrations_selected_scope()

    assert app.events == [("selected_page_indices",)]
    assert app.started is None
    assert infos == []


def test_crop_entry_syncs_writes_loads_settings_then_delegates(monkeypatch) -> None:
    app = _CropApp()
    _stub_info(monkeypatch)

    def fake_write_ppp(path, polygons, stem):
        app.events.append(("write_ppp", path, polygons, stem))

    monkeypatch.setattr(illustration_module, "write_ppp", fake_write_ppp)

    IllustrationController(app).split_illustrations_selected_scope()

    assert app.events[:4] == [
        ("selected_page_indices",),
        ("sync_polygon_label_texts",),
        ("ppp_write_path", Path("/pages/page001.png")),
        ("write_ppp", Path("/custom-ppp/page001.ppp"), app.polygons, "page001"),
    ]
    assert app.events[4] == ("load_crop_settings",)
    assert app.events[5][0] == "start_illustration_crop"
    assert app.events[5][1] == [0, 2]
    assert app.events[5][2] is app.crop_config
    assert app.started is not None
    assert app.started[0] == [0, 2]
    assert app.started[1] is app.crop_config


def test_phase4n_app_wrapper_ui_binding_and_crop_runner_boundary_are_preserved() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller = (
        ROOT / "src/picture_capture/ui/controllers/illustration.py"
    ).read_text(encoding="utf-8")
    runtime = (
        ROOT / "src/picture_capture/postproduction_single_line_runtime.py"
    ).read_text(encoding="utf-8")

    assert (
        "def split_illustrations_selected_scope(self) -> None:\n"
        "        self._illustration_controller_for_call().split_illustrations_selected_scope()"
    ) in app
    assert '("插图切图", self.split_illustrations_selected_scope)' in app
    assert "def _start_illustration_crop(self, indices: list[int], config: dict)" in app
    assert "def split_illustrations_selected_scope(self) -> None:" in controller
    assert "app._ppp_write_path(app.current_page)" in controller
    assert "app._start_illustration_crop(indices, app._load_crop_settings())" in controller
    assert "def _start_illustration_crop" not in controller
    assert "split_illustrations_job" not in controller
    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" in runtime
    assert "split_illustrations_selected_scope" not in runtime
