from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import picture_capture.ui.controllers.crop as crop_module
from picture_capture.ui.controllers.crop import CropController
from picture_capture.unlined_line_export import UnlinedPageResult


class _StatusVar:
    def __init__(self) -> None:
        self.values: list[str] = []

    def set(self, value: str) -> None:
        self.values.append(value)


class _App:
    def __init__(self) -> None:
        self._batch_active = False
        self.status_var = _StatusVar()
        self.parallel: dict[str, object] | None = None

    def _start_parallel_batch_task(
        self, title, items, worker_func, job_builder, result_consumer=None,
        on_done=None, item_label=None, max_workers=0,
    ) -> bool:
        self.parallel = {
            "title": title,
            "items": list(items),
            "worker_func": worker_func,
            "job_builder": job_builder,
            "result_consumer": result_consumer,
            "on_done": on_done,
            "item_label": item_label,
            "max_workers": max_workers,
        }
        return True


def test_unlined_busy_short_circuits_before_snapshot(monkeypatch):
    app = _App()
    app._batch_active = True
    monkeypatch.setattr(
        crop_module,
        "_snapshot_scope",
        lambda _app: (_ for _ in ()).throw(AssertionError("snapshot must not run")),
    )

    CropController(app).export_unlined_rows_selected_scope()

    assert app.parallel is None
    assert app.status_var.values == ["已有批量任务正在运行，请结束后再导出未画线行。"]


def test_unlined_action_uses_shared_runner_and_runtime_fast_path_indirection(tmp_path, monkeypatch):
    app = _App()
    project_root = tmp_path / "project"
    images = (project_root / "p1.jpg", project_root / "p2.jpg")
    settings = SimpleNamespace(marker=7)
    states: list[bool] = []

    def sentinel_worker(*_args):
        raise AssertionError("not executed in orchestration test")

    monkeypatch.setattr(crop_module, "_snapshot_scope", lambda _app: (project_root, images, (1, 0), settings))
    monkeypatch.setattr(crop_module, "configured_single_line_workers", lambda _root: 4)
    monkeypatch.setattr(crop_module, "load_merge_by_page", lambda _root: True)
    monkeypatch.setattr(crop_module, "load_unlined_filter_settings", lambda _root: (True, True, 1.2))
    monkeypatch.setattr(crop_module, "_set_unlined_job_button_state", lambda _app, active: states.append(bool(active)))
    monkeypatch.setattr(crop_module.unlined_export, "export_unlined_page_job", sentinel_worker)

    CropController(app).export_unlined_rows_selected_scope()

    assert app.parallel is not None
    assert app.parallel["title"] == "未画线行导出"
    assert app.parallel["items"] == [1, 0]
    assert app.parallel["worker_func"] is sentinel_worker
    assert app.parallel["max_workers"] == 2
    assert app.parallel["item_label"](1) == "p2.jpg"
    assert states == [True]
    assert app.status_var.values[-1] == "未画线行导出：准备分析 2 页（并行×2；仅近空白≤1.2%墨迹）…"

    payload = app.parallel["job_builder"](1, 1, 2)
    assert payload == (
        str(project_root), str(images[1]), 1, settings,
        True, True, True, 1.2,
    )
    assert (project_root / "QT" / "PSW_UNLINED").is_dir()


def test_unlined_done_aggregates_success_and_restores_buttons(tmp_path, monkeypatch):
    app = _App()
    project_root = tmp_path / "project"
    images = (project_root / "p1.jpg", project_root / "p2.jpg")
    states: list[bool] = []
    monkeypatch.setattr(crop_module, "_snapshot_scope", lambda _app: (project_root, images, (0, 1), SimpleNamespace()))
    monkeypatch.setattr(crop_module, "configured_single_line_workers", lambda _root: 2)
    monkeypatch.setattr(crop_module, "load_merge_by_page", lambda _root: True)
    monkeypatch.setattr(crop_module, "load_unlined_filter_settings", lambda _root: (True, True, 0.8))
    monkeypatch.setattr(crop_module, "_set_unlined_job_button_state", lambda _app, active: states.append(bool(active)))

    CropController(app).export_unlined_rows_selected_scope()
    assert app.parallel is not None
    done = app.parallel["on_done"]
    results = [
        UnlinedPageResult(0, "p1.jpg", 10, 3, 7, 1, 2, 5, True, True),
        UnlinedPageResult(1, "p2.jpg", 0, 0, 0, 0, 0, 0, False, False),
    ]
    done(2, 2, False, results, None)

    assert states == [True, False]
    assert app.status_var.values[-1] == (
        f"未画线行导出完成：2 页，发现 7 个未画线行，输出 1 张；空白过滤≤0.8%墨迹；"
        f"按页合并；Layout不可靠跳过 1 页；并行×2；保存到 {project_root / 'QT' / 'PSW_UNLINED'}"
    )


def test_unlined_stopped_and_error_paths_restore_buttons(tmp_path, monkeypatch):
    app = _App()
    project_root = tmp_path / "project"
    images = (project_root / "p1.jpg", project_root / "p2.jpg")
    states: list[bool] = []
    monkeypatch.setattr(crop_module, "_snapshot_scope", lambda _app: (project_root, images, (0, 1), SimpleNamespace()))
    monkeypatch.setattr(crop_module, "configured_single_line_workers", lambda _root: 1)
    monkeypatch.setattr(crop_module, "load_merge_by_page", lambda _root: False)
    monkeypatch.setattr(crop_module, "load_unlined_filter_settings", lambda _root: (False, False, 0.8))
    monkeypatch.setattr(crop_module, "_set_unlined_job_button_state", lambda _app, active: states.append(bool(active)))

    CropController(app).export_unlined_rows_selected_scope()
    assert app.parallel is not None
    done = app.parallel["on_done"]
    result = UnlinedPageResult(0, "p1.jpg", 10, 4, 6, 6, 0, 0, False, True)
    done(1, 2, True, [result], None)
    assert states == [True, False]
    assert app.status_var.values[-1] == (
        "未画线行导出已停止：完成 1/2 页，发现 6 个未画线行，输出 6 张；串行"
    )

    before = list(app.status_var.values)
    done(1, 2, True, [result], (RuntimeError("boom"), "trace"))
    assert states == [True, False, False]
    assert app.status_var.values == before


def test_controller_looks_up_unlined_worker_through_module_for_fast_path_patch():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/picture_capture/ui/controllers/crop.py").read_text(encoding="utf-8")
    assert "from ... import unlined_line_export as unlined_export" in source
    assert "unlined_export.export_unlined_page_job" in source
    assert "from ...unlined_line_export import export_unlined_page_job" not in source
