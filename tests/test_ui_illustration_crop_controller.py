from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

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


@dataclass
class _RunnerSettings:
    start_y: int = 17
    crop_parallel_workers: int = 6


class _RunnerApp:
    def __init__(self) -> None:
        self._batch_active = False
        self.project = SimpleNamespace(
            root=Path("/project"),
            images=[Path("/pages/page001.png"), Path("/pages/page002.png")],
        )
        self.settings = _RunnerSettings()
        self.status_var = _StatusVar()
        self.ppp_reads: list[Path] = []
        self.parallel: dict[str, object] | None = None

    def _ppp_read_path(self, page: Path) -> Path:
        self.ppp_reads.append(page)
        return Path("/custom-ppp-read") / f"{page.stem}.ppp"

    def _start_parallel_batch_task(
        self, title, items, worker, job_builder, consume_result, done, *, item_label, max_workers
    ) -> bool:
        self.parallel = {
            "title": title,
            "items": list(items),
            "worker": worker,
            "job_builder": job_builder,
            "consume_result": consume_result,
            "done": done,
            "item_label": item_label,
            "max_workers": max_workers,
        }
        return True


def test_phase4o_runner_preserves_no_project_and_batch_active_guards() -> None:
    app = _RunnerApp()
    app.project = None
    IllustrationController(app)._start_illustration_crop([0], {})
    assert app.parallel is None
    assert app.status_var.values == []

    app = _RunnerApp()
    app._batch_active = True
    IllustrationController(app)._start_illustration_crop([0], {})
    assert app.parallel is None
    assert app.status_var.values == ["已有批量任务正在运行，未启动插图切图。"]


def test_phase4o_runner_snapshots_settings_and_preserves_default_payload(monkeypatch) -> None:
    app = _RunnerApp()
    monkeypatch.setattr(illustration_module, "qt_root", lambda _root: Path("/qt-root"))
    monkeypatch.setattr(illustration_module, "pdic_path", lambda page: Path("/pdic") / f"{page.stem}.pdic")

    def fake_worker(*_args):
        return None

    monkeypatch.setattr(illustration_module, "split_illustrations_job", fake_worker)
    IllustrationController(app)._start_illustration_crop([0, 1], {})

    assert app.parallel is not None
    assert app.parallel["title"] == "插图切图"
    assert app.parallel["items"] == [0, 1]
    assert app.parallel["worker"] is fake_worker
    assert app.parallel["max_workers"] == 6
    assert app.parallel["item_label"](1) == "page002.png"

    app.settings.start_y = 99
    app.settings.crop_parallel_workers = 99
    payload = app.parallel["job_builder"](0, 1, 2)
    assert payload == (
        str(Path("/pages/page001.png")),
        str(Path("/custom-ppp-read/page001.ppp")),
        str(Path("/qt-root/PIC")),
        _RunnerSettings(start_y=17, crop_parallel_workers=6),
        17, 0, 0,
        str(Path("/pdic/page001.pdic")),
        0, 0, True, 0,
    )
    assert payload[3] is not app.settings
    assert app.ppp_reads == [Path("/pages/page001.png")]


def test_phase4o_runner_preserves_config_and_special_page_overrides(monkeypatch) -> None:
    app = _RunnerApp()
    monkeypatch.setattr(illustration_module, "qt_root", lambda _root: Path("/qt-root"))
    monkeypatch.setattr(illustration_module, "pdic_path", lambda page: Path("/pdic") / f"{page.stem}.pdic")
    config = {
        "general_top_y": 11,
        "general_bottom_y": 22,
        "polygon_margin": 3,
        "entry_left_padding_x": 4,
        "entry_right_padding_x": 5,
        "integrate_illustrations": False,
        "special_pages": {"page002": {"top_y": 91, "bottom_y": 192}},
        "parallel_workers": 7,
    }
    IllustrationController(app)._start_illustration_crop([0, 1], config)
    assert app.parallel is not None
    assert app.parallel["max_workers"] == 7

    general = app.parallel["job_builder"](0, 1, 2)
    special = app.parallel["job_builder"](1, 2, 2)
    assert general[4:12] == (11, 22, 3, str(Path("/pdic/page001.pdic")), 4, 5, False, 0)
    assert special[4:12] == (91, 192, 3, str(Path("/pdic/page002.pdic")), 4, 5, False, 1)


def test_phase4o_runner_preserves_result_logging_and_counts(monkeypatch) -> None:
    app = _RunnerApp()
    crop_logs: list[tuple] = []
    illustration_logs: list[tuple] = []
    monkeypatch.setattr(
        illustration_module, "append_crop_log",
        lambda root, records: crop_logs.append((root, list(records))),
    )
    monkeypatch.setattr(
        illustration_module, "append_illustration_crop_log",
        lambda root, events: illustration_logs.append((root, list(events))),
    )
    IllustrationController(app)._start_illustration_crop([0], {})
    assert app.parallel is not None
    consume = app.parallel["consume_result"]

    result = SimpleNamespace(records=("r1", "r2"), events=("e1",))
    assert consume(0, result) == 2
    assert crop_logs == [(Path("/project"), ["r1", "r2"])]
    assert illustration_logs == [(Path("/project"), ["e1"])]

    assert consume(0, SimpleNamespace()) == 0
    assert crop_logs[-1] == (Path("/project"), [])
    assert illustration_logs[-1] == (Path("/project"), [])


def test_phase4o_runner_preserves_done_status_and_error_noop() -> None:
    app = _RunnerApp()
    IllustrationController(app)._start_illustration_crop([0], {})
    assert app.parallel is not None
    done = app.parallel["done"]

    done(1, 2, False, [4], RuntimeError("failed"))
    assert app.status_var.values == []

    done(1, 2, True, [2, None, 3], None)
    assert app.status_var.values[-1] == "插图切图已停止：完成 1/2 页，共导出 5 张"

    done(2, 2, False, [1, 2], None)
    assert app.status_var.values[-1] == "插图切图完成：2 页，共 3 张"


def test_phase4o_app_wrapper_ui_binding_and_crop_runner_boundary_are_preserved() -> None:
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
    app_runner_start = app.index("    def _start_illustration_crop(")
    app_runner_end = app.index("    def build_picdic(", app_runner_start)
    app_runner_block = app[app_runner_start:app_runner_end]
    assert "self._illustration_controller_for_call()._start_illustration_crop(indices, config)" in app_runner_block
    assert "def split_illustrations_selected_scope(self) -> None:" in controller
    assert "app._ppp_write_path(app.current_page)" in controller
    assert "app._start_illustration_crop(indices, app._load_crop_settings())" in controller
    assert "def _start_illustration_crop(self, indices: list[int], config: dict)" in controller
    assert "app._start_parallel_batch_task(" in controller
    assert "def _start_parallel_batch_task" not in controller
    assert "split_illustrations_job" in controller
    assert "append_illustration_crop_log" in controller
    assert "split_illustrations_job," not in app[: app.index("class PictureCaptureApp")]
    assert "append_illustration_crop_log," not in app[: app.index("class PictureCaptureApp")]
    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" in runtime
    assert "split_illustrations_selected_scope" not in runtime
