from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


runtime_path = ROOT / "src/picture_capture/postproduction_single_line_runtime.py"
runtime_path.write_text(
    '''from __future__ import annotations

"""Shared preflight helpers for post-production single-line actions.

Phase 5D moved the main selected-scope single-line worker onto the app-owned
batch runner.  The remaining helpers are intentionally retained here because
the still-runtime-owned unlined export reuses the same selected-scope snapshot
and button/status adapters.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any
import tkinter as tk

from .ordinary_action_runtime import _apply_quick_settings_for_ordinary


def _set_job_button_state(app: Any, active: bool) -> None:
    button = getattr(app, "_pc_single_line_crop_button", None)
    if button is None:
        return
    try:
        button.configure(state="disabled" if active else "normal")
    except tk.TclError:
        pass


def _status(app: Any, text: str) -> None:
    try:
        app.status_var.set(text)
    except Exception:
        pass


def _snapshot_scope(app: Any) -> tuple[Path, tuple[Path, ...], tuple[int, ...], Any] | None:
    if not app.guard():
        return None
    # Single-line export is OCR-independent. Reuse the ordinary-action settings
    # adapter so a project with every OCR engine disabled is still allowed to
    # apply current quick geometry before cropping.
    if not _apply_quick_settings_for_ordinary(app):
        return None

    save_current = getattr(app, "save_current_page", None)
    if callable(save_current):
        save_current()

    project = getattr(app, "project", None)
    if project is None:
        return None
    indices = tuple(int(index) for index in app.selected_page_indices())
    if not indices:
        _status(app, "单行切图：当前没有可处理的选定页面。")
        return None
    images = tuple(Path(path) for path in project.images)
    valid = tuple(index for index in indices if 0 <= index < len(images))
    if not valid:
        _status(app, "单行切图：选定范围内没有有效页面。")
        return None
    return Path(project.root), images, valid, replace(app.settings)


__all__ = []
''',
    encoding="utf-8",
)

crop_path = ROOT / "src/picture_capture/ui/controllers/crop.py"
replace_once(
    crop_path,
    "remain outside this controller. The selected-scope single-line action is explicit\n"
    "here, while its temporary Tk worker/poll scheduler remains runtime-owned.\n",
    "remain outside this controller. The selected-scope single-line action is explicit\n"
    "here and uses the app-owned parallel batch runner; shared preflight helpers remain\n"
    "temporary until the separate unlined-export runtime is decomposed.\n",
)
replace_once(
    crop_path,
    "from ...postproduction_single_line_runtime import start_single_line_export\n",
    "from ...postproduction_single_line_runtime import (\n"
    "    _set_job_button_state, _snapshot_scope, _status,\n"
    ")\n",
)
replace_once(
    crop_path,
    "from ...project_storage import ppp_read_path_for_image, qt_root\n",
    "from ...project_storage import ppp_read_path_for_image, qt_root\n"
    "from ...single_line_merge_settings import load_merge_by_page\n"
    "from ...single_line_parallel import configured_single_line_workers, single_line_page_job\n",
)
replace_once(
    crop_path,
    '''    def split_single_lines_selected_scope(self) -> None:\n        """Start selected-scope single-line export through the retained Tk scheduler."""\n        start_single_line_export(self.app)\n''',
    '''    def split_single_lines_selected_scope(self) -> None:\n        """Export selected-page single lines through the shared app batch runner."""\n        app = self.app\n        if bool(getattr(app, "_batch_active", False)):\n            _status(app, "已有批量任务正在运行，请结束后再执行单行切图。")\n            return\n\n        snapshot = _snapshot_scope(app)\n        if snapshot is None:\n            return\n        project_root, images, indices, settings = snapshot\n        output_dir = qt_root(project_root) / "PSW"\n        output_dir.mkdir(parents=True, exist_ok=True)\n        merge_by_page = load_merge_by_page(project_root)\n        workers = max(1, min(configured_single_line_workers(project_root), len(indices)))\n        worker_text = "串行" if workers <= 1 else f"并行×{workers}"\n        _status(app, f"单行切图：准备处理 {len(indices)} 页（{worker_text}）…")\n        _set_job_button_state(app, True)\n\n        def job_builder(index: int, _position: int, _total: int):\n            return (\n                str(project_root),\n                str(images[index]),\n                int(index),\n                settings,\n                str(output_dir),\n                bool(merge_by_page),\n            )\n\n        def consume_result(_index: int, result):\n            _page_index, filename, records, merged = result\n            append_crop_log(project_root, records)\n            return filename, len(records), bool(merged)\n\n        def done(completed, total_pages, stopped, results, error):\n            _set_job_button_state(app, False)\n            if error is not None:\n                return\n            record_count = sum(int(result[1]) for result in results)\n            if stopped:\n                _status(\n                    app,\n                    f"单行切图已停止：完成 {completed}/{total_pages} 页，共 {record_count} 行；{worker_text}",\n                )\n                return\n            mode = "；每页已合并为 1 张图" if merge_by_page else ""\n            _status(\n                app,\n                f"单行切图完成：{completed} 页，共 {record_count} 行{mode}；{worker_text}；已保存到 {output_dir}",\n            )\n\n        started = app._start_parallel_batch_task(\n            "单行切图",\n            indices,\n            single_line_page_job,\n            job_builder,\n            consume_result,\n            done,\n            item_label=lambda index: images[index].name,\n            max_workers=workers,\n        )\n        if not started:\n            _set_job_button_state(app, False)\n''',
)

runtime_test = ROOT / "tests/test_postproduction_single_line_runtime.py"
runtime_test.write_text(
    '''from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from picture_capture.models import Entry
import picture_capture.postproduction_single_line_runtime as runtime
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
    monkeypatch.setattr(
        parallel.formats,
        "read_pdic",
        lambda path: [Entry(path.stem, 10, 20)],
    )
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
        root,
        images,
        (1, 0),
        settings,
        lambda *args: progress.append(tuple(args)),
    )

    assert [call["image_path"].name for call in calls] == ["page2.jpg", "page1.jpg"]
    assert [call["profile_page_index"] for call in calls] == [1, 0]
    assert [call["page_sections"] for call in calls] == [
        ["section:page2"],
        ["section:page1"],
    ]
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
        self,
        title,
        items,
        worker_func,
        job_builder,
        result_consumer=None,
        on_done=None,
        item_label=None,
        max_workers=0,
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

    monkeypatch.setattr(
        crop_module,
        "_snapshot_scope",
        lambda _app: (project_root, images, (1, 0), settings),
    )
    monkeypatch.setattr(crop_module, "configured_single_line_workers", lambda _root: 4)
    monkeypatch.setattr(crop_module, "load_merge_by_page", lambda _root: True)
    monkeypatch.setattr(
        crop_module,
        "_set_job_button_state",
        lambda _app, active: button_states.append(bool(active)),
    )
    monkeypatch.setattr(
        crop_module,
        "append_crop_log",
        lambda _root, records: logged.append(list(records)),
    )

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
        str(project_root),
        str(images[1]),
        1,
        settings,
        str(project_root / "QT" / "PSW"),
        True,
    )

    records = [object(), object(), object()]
    consumed = app.parallel["result_consumer"](
        1,
        (1, "p2.jpg", records, True),
    )
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
    monkeypatch.setattr(
        crop_module,
        "_snapshot_scope",
        lambda _app: (project_root, images, (0, 1), SimpleNamespace()),
    )
    monkeypatch.setattr(crop_module, "configured_single_line_workers", lambda _root: 1)
    monkeypatch.setattr(crop_module, "load_merge_by_page", lambda _root: False)
    monkeypatch.setattr(crop_module, "_set_job_button_state", lambda _app, active: states.append(active))

    CropController(app).split_single_lines_selected_scope()
    assert app.parallel is not None
    app.parallel["on_done"](1, 2, True, [("p1.jpg", 4, False)], None)

    assert states == [True, False]
    assert app.status_var.values[-1] == "单行切图已停止：完成 1/2 页，共 4 行；串行"


def test_runtime_is_preflight_only_after_phase5d():
    root = Path(__file__).resolve().parents[1]
    runtime_source = (root / "src/picture_capture/postproduction_single_line_runtime.py").read_text(
        encoding="utf-8"
    )
    controller_source = (
        root / "src/picture_capture/ui/controllers/crop.py"
    ).read_text(encoding="utf-8")
    app_source = (root / "src/picture_capture/app.py").read_text(encoding="utf-8")

    assert "def _snapshot_scope(app: Any)" in runtime_source
    assert "threading.Thread(" not in runtime_source
    assert "queue.Queue" not in runtime_source
    assert "def start_single_line_export(" not in runtime_source
    assert "app.after(80, poll)" not in runtime_source
    assert "_pc_single_line_crop_active" not in runtime_source
    assert "_pc_single_line_crop_token" not in runtime_source
    assert "_pc_single_line_crop_thread" not in runtime_source
    assert "app._start_parallel_batch_task(" in controller_source
    assert "single_line_page_job" in controller_source
    assert "_snapshot_scope(app)" in controller_source
    assert "def _start_parallel_batch_task(" in app_source


def test_runtime_contract_keeps_main_button_left_of_entry_crop_and_selected_scope_wrapper():
    root = Path(__file__).resolve().parents[1]
    app_source = (root / "src/picture_capture/app.py").read_text(encoding="utf-8")

    assert (
        '(("单行切图", self.split_single_lines_selected_scope), '
        '("词条切图", self.split_entries_selected_scope), '
        '("插图切图", self.split_illustrations_selected_scope))'
    ) in app_source
    assert 'if text == "单行切图":' in app_source
    assert "self._pc_single_line_crop_button = button" in app_source
    assert "def split_single_lines_selected_scope(self)" in app_source
    assert "self._crop_controller_for_call().split_single_lines_selected_scope()" in app_source


def test_gui_composition_no_longer_installs_single_line_ui_runtime():
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src" / "picture_capture" / "bootstrap" / "gui.py"
    ).read_text(encoding="utf-8")
    assert "install_postproduction_single_line_runtime" not in source
    assert "install_unlined_line_export_ui(app_module)" in source
''',
    encoding="utf-8",
)

crop_test = ROOT / "tests/test_ui_crop_controller.py"
replace_once(
    crop_test,
    '''def test_selected_scope_single_line_routes_to_retained_runtime_scheduler(monkeypatch) -> None:\n    app = _App()\n    calls: list[object] = []\n    monkeypatch.setattr(crop_module, "start_single_line_export", lambda value: calls.append(value))\n\n    CropController(app).split_single_lines_selected_scope()\n\n    assert calls == [app]\n''',
    '''def test_selected_scope_single_line_routes_to_shared_parallel_batch_runner() -> None:\n    source = (ROOT / "src/picture_capture/ui/controllers/crop.py").read_text(encoding="utf-8")\n    tree = ast.parse(source)\n    crop_class = next(\n        node for node in tree.body\n        if isinstance(node, ast.ClassDef) and node.name == "CropController"\n    )\n    method = next(\n        node for node in crop_class.body\n        if isinstance(node, ast.FunctionDef) and node.name == "split_single_lines_selected_scope"\n    )\n    method_text = ast.get_source_segment(source, method) or ""\n\n    assert "_snapshot_scope(app)" in method_text\n    assert "app._start_parallel_batch_task(" in method_text\n    assert "single_line_page_job" in method_text\n    assert "start_single_line_export" not in method_text\n''',
)

parallel_test = ROOT / "tests/test_single_line_parallel.py"
replace_once(
    parallel_test,
    '''def test_main_single_line_runtime_reports_effective_parallelism():\n    source = (\n        Path(__file__).resolve().parents[1]\n        / "src" / "picture_capture" / "postproduction_single_line_runtime.py"\n    ).read_text(encoding="utf-8")\n\n    assert "run_single_line_pages(" in source\n    assert "configured_single_line_workers(project_root)" in source\n    assert 'f"并行×{workers}"' in source\n    assert "split_single_lines(" not in source\n    assert "merge_page_line_images(" not in source\n''',
    '''def test_main_single_line_controller_reports_effective_parallelism_through_shared_runner():\n    source = (\n        Path(__file__).resolve().parents[1]\n        / "src" / "picture_capture" / "ui" / "controllers" / "crop.py"\n    ).read_text(encoding="utf-8")\n\n    assert "configured_single_line_workers(project_root)" in source\n    assert 'f"并行×{workers}"' in source\n    assert "single_line_page_job" in source\n    assert "app._start_parallel_batch_task(" in source\n    assert "run_single_line_pages(" not in source\n''',
)

print("Phase 5D patch applied")
