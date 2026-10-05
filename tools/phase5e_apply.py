from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# ---------------------------------------------------------------------------
# CropController: retire the temporary helper runtime, keep fast-path worker
# lookup indirect, and move the unlined action onto the shared batch runner.
# ---------------------------------------------------------------------------
crop_path = ROOT / "src/picture_capture/ui/controllers/crop.py"
replace_once(
    crop_path,
    '''Crop geometry and file generation remain in ``processing`` and project path
policy remains in ``project_storage``. Crop-settings UI and illustration actions
remain outside this controller. The selected-scope single-line action is explicit
here and uses the app-owned parallel batch runner; shared preflight helpers remain
temporary until the separate unlined-export runtime is decomposed.
''',
    '''Crop geometry and file generation remain in ``processing`` and project path
policy remains in ``project_storage``. Crop-settings UI and illustration actions
remain outside this controller. Selected-scope single-line and unlined-row export
actions are explicit here and use the app-owned parallel batch runner.
''',
)
replace_once(
    crop_path,
    '''from dataclasses import replace
from typing import Any

from ...formats import pdic_path, read_pdic, read_ppp
from ...postproduction_single_line_runtime import (
    _set_job_button_state, _snapshot_scope, _status,
)
from ...processing import (
''',
    '''from dataclasses import replace
from pathlib import Path
from typing import Any
import tkinter as tk

from ... import unlined_line_export as unlined_export
from ...formats import pdic_path, read_pdic, read_ppp
from ...ordinary_action_runtime import _apply_quick_settings_for_ordinary
from ...processing import (
''',
)
replace_once(
    crop_path,
    '''from ...single_line_parallel import configured_single_line_workers, single_line_page_job


class CropController:
''',
    '''from ...single_line_parallel import configured_single_line_workers, single_line_page_job
from ...unlined_export_filter_settings import load_unlined_filter_settings


def _status(app: Any, text: str) -> None:
    try:
        app.status_var.set(text)
    except Exception:
        pass


def _set_button_state(app: Any, names: tuple[str, ...], active: bool) -> None:
    for name in names:
        button = getattr(app, name, None)
        if button is None:
            continue
        try:
            button.configure(state="disabled" if active else "normal")
        except tk.TclError:
            pass


def _set_job_button_state(app: Any, active: bool) -> None:
    """Preserve the main single-line action's historical button-state contract."""
    _set_button_state(app, ("_pc_single_line_crop_button",), active)


def _set_unlined_job_button_state(app: Any, active: bool) -> None:
    """Disable both related exporters while unlined-row export is active."""
    _set_button_state(
        app,
        ("_pc_unlined_export_button", "_pc_single_line_crop_button"),
        active,
    )


def _snapshot_scope(app: Any) -> tuple[Path, tuple[Path, ...], tuple[int, ...], Any] | None:
    if not app.guard():
        return None
    # Both selected-scope exporters are OCR-independent. Reuse the ordinary
    # action adapter so projects with all OCR engines disabled can still apply
    # current quick geometry before cropping/export.
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


class CropController:
''',
)
unlined_method = '''
    def export_unlined_rows_selected_scope(self) -> None:
        """Export selected-page Layout rows without current PDIC markers."""
        app = self.app
        if bool(getattr(app, "_batch_active", False)):
            _status(app, "已有批量任务正在运行，请结束后再导出未画线行。")
            return

        snapshot = _snapshot_scope(app)
        if snapshot is None:
            return
        project_root, images, indices, settings = snapshot
        output_dir = qt_root(project_root) / unlined_export.OUTPUT_DIRNAME
        output_dir.mkdir(parents=True, exist_ok=True)
        merge_by_page = load_merge_by_page(project_root)
        filter_enabled, filter_blank, blank_threshold = load_unlined_filter_settings(
            project_root
        )
        workers = max(1, min(configured_single_line_workers(project_root), len(indices)))
        worker_text = "串行" if workers <= 1 else f"并行×{workers}"
        filter_text = (
            f"；仅近空白≤{blank_threshold:g}%墨迹"
            if filter_enabled and filter_blank
            else ""
        )
        _status(
            app,
            f"未画线行导出：准备分析 {len(indices)} 页（{worker_text}{filter_text}）…",
        )
        _set_unlined_job_button_state(app, True)

        def job_builder(index: int, _position: int, _total: int):
            return (
                str(project_root),
                str(images[index]),
                int(index),
                settings,
                bool(merge_by_page),
                bool(filter_enabled),
                bool(filter_blank),
                float(blank_threshold),
            )

        def done(completed, total_pages, stopped, results, error):
            _set_unlined_job_button_state(app, False)
            if error is not None:
                return

            total_unlined = sum(int(result.unlined_rows) for result in results)
            total_exported = sum(int(result.exported_images) for result in results)
            unreliable = sum(
                1 for result in results if not bool(result.physical_reliable)
            )
            mode = "；按页合并" if merge_by_page else ""
            filtered = (
                f"；空白过滤≤{blank_threshold:g}%墨迹"
                if filter_enabled and filter_blank
                else ""
            )
            skipped = f"；Layout不可靠跳过 {unreliable} 页" if unreliable else ""
            if stopped:
                _status(
                    app,
                    f"未画线行导出已停止：完成 {completed}/{total_pages} 页，"
                    f"发现 {total_unlined} 个未画线行，输出 {total_exported} 张"
                    f"{filtered}{mode}{skipped}；{worker_text}",
                )
                return
            _status(
                app,
                f"未画线行导出完成：{completed} 页，发现 {total_unlined} 个未画线行，"
                f"输出 {total_exported} 张{filtered}{mode}{skipped}；"
                f"{worker_text}；保存到 {output_dir}",
            )

        # Deliberately resolve the one-page worker through the module at action
        # time. GUI composition installs the physical-row fast path after app.py
        # (and therefore this controller) is imported; importing the function by
        # value here would freeze the pre-fast-path worker and regress performance.
        started = app._start_parallel_batch_task(
            "未画线行导出",
            indices,
            unlined_export.export_unlined_page_job,
            job_builder,
            on_done=done,
            item_label=lambda index: images[index].name,
            max_workers=workers,
        )
        if not started:
            _set_unlined_job_button_state(app, False)

'''
replace_once(
    crop_path,
    '''    def split_lines_current(self) -> None:
''',
    unlined_method + '''    def split_lines_current(self) -> None:
''',
)

# ---------------------------------------------------------------------------
# PictureCaptureApp: construct the button normally and expose a compatibility
# wrapper, matching the explicit single-line path established in Phase 5C/5D.
# ---------------------------------------------------------------------------
app_path = ROOT / "src/picture_capture/app.py"
replace_once(
    app_path,
    '''            "单行切图": (
                "将【选定范围】内各页按校对界面相同的单行裁切逻辑批量输出到 QT/PSW；"
                "可在【设置中心 → 切图】选择是否按页合并，并复用切图并行进程数。"
            ),
            "词条切图": "按所选页面范围和【设置中心 → 切图】生成完整词条切图。",
''',
    '''            "单行切图": (
                "将【选定范围】内各页按校对界面相同的单行裁切逻辑批量输出到 QT/PSW；"
                "可在【设置中心 → 切图】选择是否按页合并，并复用切图并行进程数。"
            ),
            "未画线行导出": (
                "将【选定范围】内 Layout 已恢复、但当前 PDIC 没有横线的文字行导出到 QT/PSW_UNLINED。"
                "可在【设置中心 → 切图】启用【未画线行导出过滤 → 空白】只检查近空白候选；"
                "不以 entry/body 角色决定是否导出，并复用按页合并和切图并行进程设置。"
            ),
            "词条切图": "按所选页面范围和【设置中心 → 切图】生成完整词条切图。",
''',
)
replace_once(
    app_path,
    '''            (("单行切图", self.split_single_lines_selected_scope), ("词条切图", self.split_entries_selected_scope), ("插图切图", self.split_illustrations_selected_scope)),
''',
    '''            (("单行切图", self.split_single_lines_selected_scope), ("未画线行导出", self.export_unlined_rows_selected_scope), ("词条切图", self.split_entries_selected_scope), ("插图切图", self.split_illustrations_selected_scope)),
''',
)
replace_once(
    app_path,
    '''                if text == "单行切图":
                    self._pc_single_line_crop_button = button
                tooltip = production_tooltips.get(text)
''',
    '''                if text == "单行切图":
                    self._pc_single_line_crop_button = button
                elif text == "未画线行导出":
                    self._pc_unlined_export_button = button
                tooltip = production_tooltips.get(text)
''',
)
replace_once(
    app_path,
    '''    def split_single_lines_selected_scope(self) -> None:
        self._crop_controller_for_call().split_single_lines_selected_scope()

    def split_whole_current(self) -> None:
''',
    '''    def split_single_lines_selected_scope(self) -> None:
        self._crop_controller_for_call().split_single_lines_selected_scope()

    def export_unlined_rows_selected_scope(self) -> None:
        self._crop_controller_for_call().export_unlined_rows_selected_scope()

    def split_whole_current(self) -> None:
''',
)

# ---------------------------------------------------------------------------
# GUI composition: the unlined action/button is no longer runtime-installed.
# Fast-path worker installation stays exactly where it is.
# ---------------------------------------------------------------------------
gui_path = ROOT / "src/picture_capture/bootstrap/gui.py"
replace_once(
    gui_path,
    '''    from ..unlined_fast_path_runtime import install_unlined_fast_path
    from ..unlined_line_export_ui import install_unlined_line_export_ui
    from ..layout_illustration_mask_runtime import install_layout_illustration_mask_ui
''',
    '''    from ..unlined_fast_path_runtime import install_unlined_fast_path
    from ..layout_illustration_mask_runtime import install_layout_illustration_mask_ui
''',
)
replace_once(
    gui_path,
    '''    # Unlined QA now resolves physical rows from LayoutRows cache/Profile
    # projection before allowing any full Layout/Paddle fallback.
    install_unlined_fast_path()
    # The app now constructs 【单行切图】 in its normal postproduction row.
    # The unlined-row installer can therefore resolve that concrete button
    # after normal app construction and insert itself immediately to its right.
    install_unlined_line_export_ui(app_module)
    install_app_tooltip_terminology(app_module)
''',
    '''    # Unlined QA resolves physical rows from LayoutRows cache/Profile
    # projection before allowing any full Layout/Paddle fallback. CropController
    # resolves the worker through the module at action time so this post-import
    # replacement remains effective without a UI/action installer.
    install_unlined_fast_path()
    install_app_tooltip_terminology(app_module)
''',
)

# Ratchet the architecture guard: once the helper runtime disappears, it must not
# be allowed to reappear as legacy debt.
guard_path = ROOT / "scripts/architecture_guard.py"
replace_once(
    guard_path,
    '    "postproduction_single_line_runtime.py",\n',
    '',
)

# Runtime installer/helper modules retired by this slice.
(ROOT / "src/picture_capture/postproduction_single_line_runtime.py").unlink()
(ROOT / "src/picture_capture/unlined_line_export_ui.py").unlink()

# ---------------------------------------------------------------------------
# Focused source/behavior regressions.
# ---------------------------------------------------------------------------
post_test = ROOT / "tests/test_postproduction_single_line_runtime.py"
post_test.write_text(
    '''from __future__ import annotations

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
    assert "install_unlined_fast_path()" in gui_source
''',
    encoding="utf-8",
)

unlined_controller_test = ROOT / "tests/test_ui_unlined_export_controller.py"
unlined_controller_test.write_text(
    '''from __future__ import annotations

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
''',
    encoding="utf-8",
)

# Replace the old dynamic-UI source-shape lock with the explicit Phase 5E one.
unlined_test = ROOT / "tests/test_unlined_line_export.py"
unlined_text = unlined_test.read_text(encoding="utf-8")
marker = "def test_unlined_ui_is_installed_after_single_line_button_and_reuses_parallel_crop_setting():\n"
start = unlined_text.index(marker)
unlined_text = unlined_text[:start] + '''def test_unlined_ui_is_explicit_and_reuses_parallel_crop_setting():
    root = Path(__file__).resolve().parents[1]
    composition = (
        root / "src" / "picture_capture" / "bootstrap" / "gui.py"
    ).read_text(encoding="utf-8")
    controller = (
        root / "src" / "picture_capture" / "ui" / "controllers" / "crop.py"
    ).read_text(encoding="utf-8")
    app_source = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    exporter = (root / "src" / "picture_capture" / "unlined_line_export.py").read_text(encoding="utf-8")
    filters = (root / "src" / "picture_capture" / "unlined_export_filter_settings.py").read_text(encoding="utf-8")

    assert "install_unlined_line_export_ui" not in composition
    assert "unlined_line_export_ui" not in composition
    assert "install_unlined_export_filter_settings_ui(app_module)" in composition
    assert "install_unlined_fast_path()" in composition
    assert (
        '(("单行切图", self.split_single_lines_selected_scope), '
        '("未画线行导出", self.export_unlined_rows_selected_scope), '
        '("词条切图", self.split_entries_selected_scope), '
        '("插图切图", self.split_illustrations_selected_scope))'
    ) in app_source
    assert "self._pc_single_line_crop_button = button" in app_source
    assert "self._pc_unlined_export_button = button" in app_source
    assert "def export_unlined_rows_selected_scope(self)" in app_source
    assert "def export_unlined_rows_selected_scope(self)" in controller
    assert "app._start_parallel_batch_task(" in controller
    assert "unlined_export.export_unlined_page_job" in controller
    assert 'OUTPUT_DIRNAME = "PSW_UNLINED"' in exporter
    # Critical semantic locks: export is Layout-minus-PDIC, and blankness is
    # measured on the original row crop before white-border trimming.
    assert 'role == "body"' not in exporter
    assert 'matched_lined_row_keys(layout, entries)' in exporter
    assert exporter.index('ink_percent = row_ink_percent(crop)') < exporter.index(
        'trimmed = _trim_white_border(crop)'
    )
    assert 'FILTER_LABEL = "未画线行导出过滤"' in filters
    assert 'BLANK_LABEL = "空白"' in filters
    assert 'DEFAULT_BLANK_INK_PERCENT = 0.8' in filters
'''
unlined_test.write_text(unlined_text, encoding="utf-8")

# Fast-path composition test: UI installer disappears, but action-time module
# lookup guarantees the post-import worker replacement is still observed.
fast_test = ROOT / "tests/test_layout_rows_fast_path.py"
replace_once(
    fast_test,
    '''    spawn = (
        root / "src" / "picture_capture" / "spawn_detection_runtime.py"
    ).read_text(encoding="utf-8")

    assert "install_layout_rows_persistence_runtime()" in gui
    assert "install_unlined_fast_path()" in gui
    assert gui.index("install_unlined_fast_path()") < gui.index(
        "install_unlined_line_export_ui(app_module)"
    )
''',
    '''    spawn = (
        root / "src" / "picture_capture" / "spawn_detection_runtime.py"
    ).read_text(encoding="utf-8")
    crop = (
        root / "src" / "picture_capture" / "ui" / "controllers" / "crop.py"
    ).read_text(encoding="utf-8")

    assert "install_layout_rows_persistence_runtime()" in gui
    assert "install_unlined_fast_path()" in gui
    assert "install_unlined_line_export_ui" not in gui
    assert "unlined_export.export_unlined_page_job" in crop
''',
)

print("Phase 5E patch applied")
