from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from picture_capture.models import Entry
import picture_capture.single_line_parallel as parallel
import picture_capture.ui.controllers.crop as crop_module
from picture_capture.ui.controllers.crop import CropController


def test_single_line_worker_reuses_proofreading_crop_path(tmp_path, monkeypatch):
    root = tmp_path / "dictionary"
    root.mkdir()
    images = (root / "page1.jpg", root / "page2.jpg")
    calls: list[dict] = []
    logged: list[list] = []
    progress: list[tuple] = []

    monkeypatch.setattr(parallel.formats, "pdic_path", lambda path: path.with_suffix(".pdic"))
    monkeypatch.setattr(parallel.formats, "read_pdic", lambda path: [Entry(path.stem, 10, 20)])
    monkeypatch.setattr(parallel, "read_page_sections", lambda path: [f"section:{path.stem}"])

    def fake_split(image_path, entries, settings, output_dir, **kwargs):
        calls.append({
            "image_path": image_path,
            "entries": entries,
            "settings": settings,
            "output_dir": output_dir,
            **kwargs,
        })
        return [f"record:{image_path.stem}"]

    monkeypatch.setattr(parallel, "split_single_lines", fake_split)
    monkeypatch.setattr(parallel, "append_crop_log", lambda _root, records: logged.append(list(records)))
    monkeypatch.setattr(parallel, "load_merge_by_page", lambda _root: False)
    monkeypatch.setattr(parallel, "configured_single_line_workers", lambda _root: 1)

    settings = object()
    result = parallel.run_single_line_pages(
        root, images, (1, 0), settings, lambda *args: progress.append(tuple(args))
    )

    assert [call["image_path"].name for call in calls] == ["page2.jpg", "page1.jpg"]
    assert [call["profile_page_index"] for call in calls] == [1, 0]
    assert [call["page_sections"] for call in calls] == [["section:page2"], ["section:page1"]]
    assert all(call["output_dir"] == root / "QT" / "PSW" for call in calls)
    assert all(call["settings"] is settings for call in calls)
    assert logged == [["record:page2"], ["record:page1"]]
    assert [item[0:2] for item in progress] == [(1, 2), (2, 2)]
    assert result[0:2] == (2, 2)
    assert result[2] == root / "QT" / "PSW"
    assert result[4] == 1


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


def test_phase5d_selected_scope_uses_shared_parallel_batch_runner(tmp_path, monkeypatch):
    app = _App()
    project_root = tmp_path / "project"
    images = (project_root / "p1.jpg", project_root / "p2.jpg")
    settings = SimpleNamespace(marker=7)
    button_states: list[bool] = []
    logged: list[list[object]] = []

    monkeypatch.setattr(crop_module, "_snapshot_scope", lambda _app: (project_root, images, (1, 0), settings))
    monkeypatch.setattr(crop_module, "configured_single_line_workers", lambda _root: 4)
    monkeypatch.setattr(crop_module, "load_merge_by_page", lambda _root: True)
    monkeypatch.setattr(crop_module, "_set_job_button_state", lambda _app, active: button_states.append(bool(active)))
    monkeypatch.setattr(crop_module, "append_crop_log", lambda _root, records: logged.append(list(records)))

    CropController(app).split_single_lines_selected_scope()

    assert app.parallel is not None
    assert app.parallel["title"] == "单行切图"
    assert app.parallel["items"] == [1, 0]
    assert app.parallel["worker_func"] is parallel.single_line_page_job
    assert app.parallel["max_workers"] == 2
    assert app.parallel["item_label"](1) == "p2.jpg"
    assert button_states == [True]
    assert app.status_var.values[-1] == "单行切图：准备处理 2 页（并行×2）…"

    payload = app.parallel["job_builder"](1, 1, 2)
    assert payload == (
        str(project_root), str(images[1]), 1, settings,
        str(project_root / "QT" / "PSW"), True,
    )

    records = [object(), object(), object()]
    consumed = app.parallel["result_consumer"](1, (1, "p2.jpg", records, True))
    assert consumed == ("p2.jpg", 3, True)
    assert logged == [records]

    app.parallel["on_done"](2, 2, False, [("p2.jpg", 3, True), ("p1.jpg", 2, True)], None)
    assert button_states == [True, False]
    assert app.status_var.values[-1] == (
        f"单行切图完成：2 页，共 5 行；每页已合并为 1 张图；并行×2；已保存到 {project_root / 'QT' / 'PSW'}"
    )


def test_phase5d_stopped_batch_restores_button_and_reports_partial_total(tmp_path, monkeypatch):
    app = _App()
    project_root = tmp_path / "project"
    images = (project_root / "p1.jpg", project_root / "p2.jpg")
    states: list[bool] = []
    monkeypatch.setattr(crop_module, "_snapshot_scope", lambda _app: (project_root, images, (0, 1), SimpleNamespace()))
    monkeypatch.setattr(crop_module, "configured_single_line_workers", lambda _root: 1)
    monkeypatch.setattr(crop_module, "load_merge_by_page", lambda _root: False)
    monkeypatch.setattr(crop_module, "_set_job_button_state", lambda _app, active: states.append(active))

    CropController(app).split_single_lines_selected_scope()
    assert app.parallel is not None
    app.parallel["on_done"](1, 2, True, [("p1.jpg", 4, False)], None)

    assert states == [True, False]
    assert app.status_var.values[-1] == "单行切图已停止：完成 1/2 页，共 4 行；串行"


def test_phase5e_retires_temporary_runtime_and_keeps_preflight_in_crop_controller():
    root = Path(__file__).resolve().parents[1]
    runtime_path = root / "src/picture_capture/postproduction_single_line_runtime.py"
    unlined_ui_path = root / "src/picture_capture/unlined_line_export_ui.py"
    controller_source = (root / "src/picture_capture/ui/controllers/crop.py").read_text(encoding="utf-8")
    guard_source = (root / "scripts/architecture_guard.py").read_text(encoding="utf-8")

    assert not runtime_path.exists()
    assert not unlined_ui_path.exists()
    assert "def _snapshot_scope(app: Any)" in controller_source
    assert "_apply_quick_settings_for_ordinary(app)" in controller_source
    assert "postproduction_single_line_runtime" not in controller_source
    assert '"postproduction_single_line_runtime.py"' not in guard_source


def test_phase5e_normal_ui_and_app_wrappers_are_explicit():
    root = Path(__file__).resolve().parents[1]
    app_source = (root / "src/picture_capture/app.py").read_text(encoding="utf-8")
    gui_source = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")

    assert (
        '(("单行切图", self.split_single_lines_selected_scope), '
        '("未画线行导出", self.export_unlined_rows_selected_scope), '
        '("词条切图", self.split_entries_selected_scope), '
        '("插图切图", self.split_illustrations_selected_scope))'
    ) in app_source
    assert 'elif text == "未画线行导出":' in app_source
    assert "self._pc_unlined_export_button = button" in app_source
    assert "def export_unlined_rows_selected_scope(self)" in app_source
    assert "self._crop_controller_for_call().export_unlined_rows_selected_scope()" in app_source
    assert "install_unlined_line_export_ui" not in gui_source
    assert "unlined_line_export_ui" not in gui_source
    assert "install_unlined_fast_path" not in gui_source
    assert "unlined_fast_path_runtime" not in gui_source
