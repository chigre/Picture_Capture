from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


# app.py: replace the historical implementation with an explicit controller wrapper.
app_path = "src/picture_capture/app.py"
app = read(app_path)
app_start = app.index("class PictureCaptureApp")
start = app.index("    def export_training_package(", app_start)
end = app.index("\n    def show_help_dialog", start)
app = (
    app[:start]
    + "    def export_training_package(self) -> None:\n"
      "        self._export_controller_for_call().export_training_package()\n"
    + app[end:]
)
write(app_path, app)


# bootstrap: stop replacing the app method at runtime.
bootstrap_path = "src/picture_capture/bootstrap/gui.py"
bootstrap = read(bootstrap_path)
bootstrap = replace_once(
    bootstrap,
    "    from ..training_export_ui import export_training_package_selected_range\n",
    "",
    label="bootstrap training-export import",
)
bootstrap = replace_once(
    bootstrap,
    "    app_module.PictureCaptureApp.export_training_package = (\n"
    "        export_training_package_selected_range\n"
    "    )\n",
    "",
    label="bootstrap training-export assignment",
)
write(bootstrap_path, bootstrap)


# training_export_ui: keep the historical callable as a compatibility shim only.
training_ui_path = "src/picture_capture/training_export_ui.py"
training_ui = read(training_ui_path)
start = training_ui.index("def export_training_package_selected_range(self) -> None:")
training_ui = (
    training_ui[:start]
    + "def export_training_package_selected_range(self) -> None:\n"
      "    \"\"\"Compatibility shim for the explicit ExportController action.\"\"\"\n"
      "    self._export_controller_for_call().export_training_package()\n"
)
write(training_ui_path, training_ui)


# ExportController: own the training-package UI/batch orchestration.
controller_path = "src/picture_capture/ui/controllers/export.py"
controller = read(controller_path)
controller = replace_once(
    controller,
    "import os\nimport threading\n",
    "import os\nimport shutil\nimport threading\n",
    label="controller stdlib imports",
)
controller = replace_once(
    controller,
    "from PIL import Image\n\nfrom ...formats import pdic_path, read_pdic, read_picdic_index_records\n",
    "from PIL import Image\n\nfrom ... import __version__\nfrom ...formats import pdic_path, read_pdic, read_picdic_index_records\n",
    label="controller version import",
)
controller = replace_once(
    controller,
    "from ...project_storage import exports_root, qt_root\n",
    "from ...project_storage import exports_root, qt_root, training_exports_root\n"
    "from ...training_export import (\n"
    "    TrainingExportCancelled, copy_project_context, export_training_page,\n"
    "    make_training_zip, write_training_manifest,\n"
    ")\n",
    label="controller training imports",
)

helper = '''\n\ndef _training_scope_label(app: Any, indices: list[int]) -> str:\n    \"\"\"Describe the already-selected main-window page scope.\"\"\"\n    if not app.project or not indices:\n        return \"无\"\n    first_name = app.project.images[indices[0]].name\n    last_name = app.project.images[indices[-1]].name\n    mode = app.page_range_var.get() if hasattr(app, \"page_range_var\") else \"current\"\n    if len(indices) == 1:\n        return first_name\n    if mode == \"to_end\":\n        return f\"当前至末页：{first_name} → {last_name}\"\n    if mode == \"specified\":\n        spec = (\n            app.page_range_spec_var.get().strip()\n            if hasattr(app, \"page_range_spec_var\") else \"\"\n        )\n        return f\"指定：{spec or (first_name + ' → ' + last_name)}\"\n    return f\"{first_name} → {last_name}\"\n'''
controller = replace_once(
    controller,
    "\n\nclass ExportController:\n",
    helper + "\n\nclass ExportController:\n",
    label="training scope helper insertion",
)

method = '''\n    def export_training_package(self) -> None:\n        \"\"\"Export supervised training pages for the main-window page scope.\"\"\"\n        app = self.app\n        if not app.project or app._batch_active:\n            if app._batch_active:\n                app.status_var.set(\"已有批量任务正在运行，请结束后再导出训练标记包。\")\n            return\n        if any(\n            str(token[0]).startswith(\"training-cleanup-\")\n            for token in app._ui_worker_active\n        ):\n            app.status_var.set(\"上一轮训练导出仍在清理临时文件；清理完成后再重新导出。\")\n            return\n        try:\n            if app.current_page is not None and app.image is not None:\n                app._save_current_page_by_mode()\n        except Exception as exc:\n            app.show_error(\"导出前保存当前页失败\", exc)\n            return\n\n        project = app.project\n        try:\n            selected = list(app.selected_page_indices())\n        except Exception as exc:\n            app.show_error(\"读取主界面页面范围失败\", exc)\n            return\n        selected = sorted(\n            {int(index) for index in selected if 0 <= int(index) < len(project.images)}\n        )\n        if not selected:\n            messagebox.showinfo(\n                \"导出训练标记包\",\n                \"主界面当前页面范围没有有效页面。请先在页面列表上方选择范围。\",\n                parent=app,\n            )\n            return\n\n        indices = [\n            index for index in selected if pdic_path(project.images[index]).exists()\n        ]\n        if not indices:\n            messagebox.showinfo(\n                \"导出训练标记包\",\n                \"主界面当前页面范围内没有已保存的 .pdic 页面。请先人工确认并保存画线结果。\",\n                parent=app,\n            )\n            return\n\n        scope_label = _training_scope_label(app, selected)\n        skipped = len(selected) - len(indices)\n        skipped_text = f\"\\n其中 {skipped} 页没有 PDIC，将自动跳过。\" if skipped else \"\"\n        if not messagebox.askyesno(\n            \"导出训练标记包\",\n            f\"使用主界面页面范围：{scope_label}\\n\"\n            f\"将导出 {len(indices)} 个已有 .pdic 的页面。{skipped_text}\\n\\n\"\n            \"每页会同时保存：\\n\"\n            \"1. 程序普通画线的自动 baseline（优先使用当时捕获的原始快照）；\\n\"\n            \"2. 当前人工增删后的最终 PDIC；\\n\"\n            \"3. added / deleted / moved / unchanged 逐条差异；\\n\"\n            \"4. 页面排版/indent family 诊断与 OCR/PPP 上下文。\\n\\n\"\n            \"如果旧页面没有历史 baseline，导出时会非破坏性重跑一次，并明确标记为 recomputed。\\n\\n\"\n            \"请确认最终 PDIC 已人工校对。继续？\",\n            parent=app,\n        ):\n            return\n\n        export_root = training_exports_root(project.root)\n        stamp = datetime.now().strftime(\"%Y%m%d_%H%M%S_%f\")\n        base_name = f\"{project.root.name}_training_{stamp}\"\n        staging = export_root / f\".{base_name}_building\"\n        zip_path = export_root / f\"{base_name}.zip\"\n        settings = replace(app.settings)\n        page_records: list[dict] = []\n        context_files: list[str] = []\n        items: list[object] = [\"__prepare__\"] + list(indices) + [\"__finalize__\"]\n        page_order = {\n            project.images[index].name: pos for pos, index in enumerate(indices)\n        }\n\n        def cleanup_partial() -> None:\n            shutil.rmtree(staging, ignore_errors=True)\n            zip_path.with_name(f\".{zip_path.name}.tmp\").unlink(missing_ok=True)\n\n        def worker(item, _position: int, _total: int):\n            try:\n                if item == \"__prepare__\":\n                    export_root.mkdir(parents=True, exist_ok=True)\n                    cleanup_partial()\n                    staging.mkdir(parents=True, exist_ok=True)\n                    context_files[:] = copy_project_context(project.root, staging)\n                    return {\"prepared\": True}\n                if item == \"__finalize__\":\n                    if app._batch_stop_event.is_set():\n                        raise TrainingExportCancelled(\"训练标记包导出已停止\")\n                    page_records.sort(\n                        key=lambda row: page_order.get(\n                            str(row.get(\"page\") or \"\"), 10**9\n                        )\n                    )\n                    write_training_manifest(\n                        staging,\n                        project_name=project.root.name,\n                        settings=settings,\n                        pages=page_records,\n                        context_files=context_files,\n                        software_version=__version__,\n                    )\n                    make_training_zip(\n                        staging, zip_path,\n                        should_stop=app._batch_stop_event.is_set,\n                    )\n                    shutil.rmtree(staging, ignore_errors=True)\n                    return {\"final_zip\": str(zip_path)}\n                index = int(item)\n                record = export_training_page(\n                    project.images[index], project.root, settings, staging, index,\n                )\n                page_records.append(record)\n                return record\n            except TrainingExportCancelled:\n                cleanup_partial()\n                return {\"cancelled\": True}\n            except Exception:\n                cleanup_partial()\n                raise\n\n        def labeler(item) -> str:\n            if item == \"__prepare__\":\n                return \"准备 staging 并复制项目上下文\"\n            if item == \"__finalize__\":\n                return \"生成 supervised dataset_manifest.json 和 ZIP\"\n            return project.images[int(item)].name\n\n        def done(_completed, _total, stopped, results, error):\n            if error is not None:\n                return\n            produced = next(\n                (\n                    str(row.get(\"final_zip\"))\n                    for row in reversed(results)\n                    if isinstance(row, dict) and row.get(\"final_zip\")\n                ),\n                \"\",\n            )\n            if produced:\n                app.status_var.set(f\"训练标记包已导出：{Path(produced).name}\")\n                messagebox.showinfo(\n                    \"导出训练标记包完成\",\n                    f\"已导出 {len(page_records)} 页。\\n\\n{produced}\",\n                    parent=app,\n                )\n                return\n            if stopped:\n                app.status_var.set(\"训练标记包已停止；正在后台清理 staging…\")\n\n                def cleanup_worker():\n                    cleanup_partial()\n                    return True\n\n                def cleanup_done(_result) -> None:\n                    if app.project is project:\n                        app.status_var.set(\n                            \"训练标记包导出已停止；未生成不完整数据包。\"\n                        )\n\n                app._start_ui_worker(\n                    f\"training-cleanup-{base_name}\",\n                    cleanup_worker, cleanup_done,\n                    lambda exc, detail: print(detail or str(exc)),\n                    wait_on_close=True,\n                )\n\n        app._start_batch_task(\n            \"导出训练标记包\", items, worker, done, item_label=labeler,\n        )\n\n'''
controller = replace_once(
    controller,
    "\n\n    def build_picdic(self) -> None:\n",
    "\n" + method + "    def build_picdic(self) -> None:\n",
    label="training export controller method insertion",
)
write(controller_path, controller)


# Update the scope regression to inspect the new owner and preserve the old shim.
test_scope_path = "tests/test_ui_terminology_and_training_scope.py"
test_scope = read(test_scope_path)
test_scope = replace_once(
    test_scope,
    "from picture_capture import profile_indent_ui, training_export_ui\n",
    "from picture_capture import profile_indent_ui, training_export_ui\n"
    "from picture_capture.ui.controllers.export import ExportController\n",
    label="scope test controller import",
)
test_scope = replace_once(
    test_scope,
    "def test_training_export_reuses_main_window_page_scope_without_second_prompt():\n"
    "    source = inspect.getsource(training_export_ui.export_training_package_selected_range)\n"
    "    assert \"self.selected_page_indices()\" in source\n"
    "    assert \"simpledialog.askstring\" not in source\n"
    "    assert \"主界面页面范围\" in source\n",
    "def test_training_export_reuses_main_window_page_scope_without_second_prompt():\n"
    "    source = inspect.getsource(ExportController.export_training_package)\n"
    "    assert \"app.selected_page_indices()\" in source\n"
    "    assert \"simpledialog.askstring\" not in source\n"
    "    assert \"主界面页面范围\" in source\n\n"
    "    shim = inspect.getsource(training_export_ui.export_training_package_selected_range)\n"
    "    assert \"_export_controller_for_call().export_training_package()\" in shim\n"
    "    assert \"_start_batch_task\" not in shim\n",
    label="scope test ownership update",
)
write(test_scope_path, test_scope)


# Add focused behavior/ownership tests for the migrated training-export action.
behavior_path = ROOT / "tests/test_ui_training_export_controller.py"
behavior_path.write_text('''from __future__ import annotations\n\nfrom pathlib import Path\nfrom types import SimpleNamespace\n\nimport picture_capture.ui.controllers.export as export_module\nfrom picture_capture.ui.controllers.export import ExportController\n\n\nclass _Var:\n    def __init__(self, value=\"current\") -> None:\n        self.value = value\n        self.values: list[str] = []\n\n    def get(self):\n        return self.value\n\n    def set(self, value):\n        self.value = value\n        self.values.append(value)\n\n\nclass _StopEvent:\n    def __init__(self) -> None:\n        self.value = False\n\n    def is_set(self) -> bool:\n        return self.value\n\n\nclass _App:\n    def __init__(self, root: Path, pages: list[Path]) -> None:\n        self.project = SimpleNamespace(root=root, images=pages)\n        self.current_page = pages[0]\n        self.image = object()\n        self.settings = SimpleNamespace(name=\"settings\")\n        self._batch_active = False\n        self._batch_stop_event = _StopEvent()\n        self._ui_worker_active = []\n        self.status_var = _Var(\"\")\n        self.page_range_var = _Var(\"current\")\n        self.page_range_spec_var = _Var(\"\")\n        self.batch = None\n        self.ui_worker = None\n        self.calls: list[tuple] = []\n        self.errors: list[tuple[str, Exception]] = []\n\n    def _save_current_page_by_mode(self) -> None:\n        self.calls.append((\"save-current\",))\n\n    def selected_page_indices(self):\n        return list(range(len(self.project.images)))\n\n    def show_error(self, title: str, exc: Exception) -> None:\n        self.errors.append((title, exc))\n\n    def _start_batch_task(self, title, items, worker, done, **kwargs):\n        self.batch = (title, list(items), worker, done, kwargs)\n        return True\n\n    def _start_ui_worker(self, *args, **kwargs):\n        self.ui_worker = (args, kwargs)\n        return True\n\n\ndef test_training_export_controller_preserves_staging_manifest_zip_and_scope(monkeypatch, tmp_path):\n    pages = [tmp_path / \"001.jpg\", tmp_path / \"002.jpg\"]\n    pages[0].with_suffix(\".pdic\").write_text(\"x\", encoding=\"utf-8\")\n    app = _App(tmp_path, pages)\n    dialogs: list[tuple] = []\n    calls: list[tuple] = []\n\n    monkeypatch.setattr(export_module, \"replace\", lambda settings: settings)\n    monkeypatch.setattr(export_module, \"training_exports_root\", lambda root: root / \"TrainingExports\")\n    monkeypatch.setattr(export_module.messagebox, \"askyesno\", lambda *a, **k: True)\n    monkeypatch.setattr(\n        export_module.messagebox, \"showinfo\",\n        lambda title, message, *, parent: dialogs.append((title, message, parent)),\n    )\n    monkeypatch.setattr(\n        export_module, \"copy_project_context\",\n        lambda root, staging: calls.append((\"context\", root, staging)) or [\"profile.json\"],\n    )\n    monkeypatch.setattr(\n        export_module, \"export_training_page\",\n        lambda page, root, settings, staging, index: {\"page\": page.name, \"index\": index},\n    )\n    monkeypatch.setattr(\n        export_module, \"write_training_manifest\",\n        lambda staging, **kwargs: calls.append((\"manifest\", staging, kwargs)),\n    )\n    monkeypatch.setattr(\n        export_module, \"make_training_zip\",\n        lambda staging, target, *, should_stop: calls.append((\"zip\", staging, target, should_stop())),\n    )\n\n    ExportController(app).export_training_package()\n\n    assert app.calls == [(\"save-current\",)]\n    assert app.batch is not None\n    title, items, worker, done, kwargs = app.batch\n    assert title == \"导出训练标记包\"\n    assert items[0] == \"__prepare__\"\n    assert items[1] == 0\n    assert items[-1] == \"__finalize__\"\n    assert len(items) == 3\n    assert kwargs[\"item_label\"](0) == \"001.jpg\"\n\n    prepared = worker(\"__prepare__\", 1, 3)\n    record = worker(0, 2, 3)\n    final = worker(\"__finalize__\", 3, 3)\n\n    assert prepared == {\"prepared\": True}\n    assert record == {\"page\": \"001.jpg\", \"index\": 0}\n    assert \"final_zip\" in final\n    assert any(row[0] == \"context\" for row in calls)\n    assert any(row[0] == \"manifest\" for row in calls)\n    assert any(row[0] == \"zip\" for row in calls)\n\n    done(3, 3, False, [prepared, record, final], None)\n    assert app.status_var.values[-1].startswith(\"训练标记包已导出：\")\n    assert dialogs[-1][0] == \"导出训练标记包完成\"\n    assert \"已导出 1 页\" in dialogs[-1][1]\n\n\ndef test_training_export_stopped_path_keeps_async_cleanup(monkeypatch, tmp_path):\n    page = tmp_path / \"001.jpg\"\n    page.with_suffix(\".pdic\").write_text(\"x\", encoding=\"utf-8\")\n    app = _App(tmp_path, [page])\n    monkeypatch.setattr(export_module, \"replace\", lambda settings: settings)\n    monkeypatch.setattr(export_module, \"training_exports_root\", lambda root: root / \"TrainingExports\")\n    monkeypatch.setattr(export_module.messagebox, \"askyesno\", lambda *a, **k: True)\n\n    ExportController(app).export_training_package()\n    assert app.batch is not None\n    done = app.batch[3]\n    done(1, 3, True, [], None)\n\n    assert app.status_var.values[-1] == \"训练标记包已停止；正在后台清理 staging…\"\n    assert app.ui_worker is not None\n    args, kwargs = app.ui_worker\n    assert str(args[0]).startswith(\"training-cleanup-\")\n    assert kwargs[\"wait_on_close\"] is True\n\n\ndef test_phase5f_training_export_ownership_is_explicit():\n    root = Path(__file__).resolve().parents[1]\n    app = (root / \"src/picture_capture/app.py\").read_text(encoding=\"utf-8\")\n    bootstrap = (root / \"src/picture_capture/bootstrap/gui.py\").read_text(encoding=\"utf-8\")\n    controller = (root / \"src/picture_capture/ui/controllers/export.py\").read_text(encoding=\"utf-8\")\n    compat = (root / \"src/picture_capture/training_export_ui.py\").read_text(encoding=\"utf-8\")\n\n    start = app.index(\"    def export_training_package(\")\n    end = app.index(\"\\n    def show_help_dialog\", start)\n    wrapper = app[start:end]\n    assert \"self._export_controller_for_call().export_training_package()\" in wrapper\n    assert \"copy_project_context\" not in wrapper\n    assert \"make_training_zip\" not in wrapper\n    assert \"PictureCaptureApp.export_training_package =\" not in bootstrap\n    assert \"export_training_package_selected_range\" not in bootstrap\n    assert \"    def export_training_package(self) -> None:\" in controller\n    assert \"app._start_batch_task(\" in controller\n    assert \"app._start_ui_worker(\" in controller\n    assert \"def export_training_package_selected_range(self) -> None:\" in compat\n    assert \"_export_controller_for_call().export_training_package()\" in compat\n''', encoding="utf-8")

print("Phase 5F migration applied")
