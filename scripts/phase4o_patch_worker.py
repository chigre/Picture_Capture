from __future__ import annotations

from pathlib import Path


APP = Path("src/picture_capture/app.py")
CTRL = Path("src/picture_capture/ui/controllers/illustration.py")
TEST_CROP = Path("tests/test_ui_illustration_crop_controller.py")
TEST_CTRL = Path("tests/test_ui_illustration_controller.py")


# 1) Narrow app helper to the historical compatibility wrapper and clean only
# imports proven action-only by live-source search.
app = APP.read_text(encoding="utf-8")
start_marker = "    def _start_illustration_crop(self, indices: list[int], config: dict) -> None:\n"
end_marker = "    def build_picdic(self) -> None:\n"
start = app.index(start_marker)
end = app.index(end_marker, start)
old_block = app[start:end]
for marker in (
    '已有批量任务正在运行，未启动插图切图。',
    'out_dir = qt_root(project.root) / "PIC"',
    'general_top_y',
    'special_pages',
    'self._ppp_read_path(page)',
    'append_crop_log(project.root, records)',
    'append_illustration_crop_log(project.root, events)',
    'self._start_parallel_batch_task(',
    'split_illustrations_job',
):
    assert marker in old_block, f"missing live helper marker: {marker}"

wrapper = '''    def _start_illustration_crop(self, indices: list[int], config: dict) -> None:\n        \"\"\"Start PPP illustration export from the shared crop-settings snapshot.\"\"\"\n        self._illustration_controller_for_call()._start_illustration_crop(indices, config)\n\n'''
app = app[:start] + wrapper + app[end:]
for line in (
    "    append_crop_log,\n",
    "    append_illustration_crop_log,\n",
    "    split_illustrations_job,\n",
):
    assert app.count(line) == 1, f"expected one action-only import: {line!r}"
    app = app.replace(line, "", 1)
APP.write_text(app, encoding="utf-8")


# 2) Move only the runner orchestration into IllustrationController.
ctrl = CTRL.read_text(encoding="utf-8")
old_doc = '''Phase 4M moved the stable selected-scope illustration detection entry seam.\nPhase 4N also moves the stable illustration-crop action entry while retaining\nthe actual crop runner on ``PictureCaptureApp``. Detection/crop algorithms\nremain outside this controller, and project path policy stays exposed through\nthe existing app compatibility boundary.\n'''
new_doc = '''Phase 4M moved the stable selected-scope illustration detection entry seam.\nPhase 4N moved the stable illustration-crop action entry. Phase 4O moves the\nbounded illustration-crop runner orchestration while retaining the parallel\nrunner and path-policy boundaries on ``PictureCaptureApp``. Detection/crop\nalgorithms remain outside this controller.\n'''
assert old_doc in ctrl
ctrl = ctrl.replace(old_doc, new_doc, 1)
assert "from ...formats import read_ppp, write_ppp\n" in ctrl
ctrl = ctrl.replace(
    "from ...formats import read_ppp, write_ppp\n",
    "from ...formats import pdic_path, read_ppp, write_ppp\n",
    1,
)
assert "from ...processing import detect_illustrations_job\n" in ctrl
ctrl = ctrl.replace(
    "from ...processing import detect_illustrations_job\n",
    "from ...processing import (\n"
    "    append_crop_log, append_illustration_crop_log, detect_illustrations_job,\n"
    "    split_illustrations_job,\n"
    ")\n"
    "from ...project_storage import qt_root\n",
    1,
)
assert "    def _start_illustration_crop" not in ctrl
insert_before = "    def detect_illustrations_selected_scope(self) -> None:\n"
assert ctrl.count(insert_before) == 1
runner = '''    def _start_illustration_crop(self, indices: list[int], config: dict) -> None:\n        \"\"\"Start PPP illustration export from the shared crop-settings snapshot.\"\"\"\n        app = self.app\n        if not app.project or app._batch_active:\n            if app._batch_active:\n                app.status_var.set(\"已有批量任务正在运行，未启动插图切图。\")\n            return\n        project = app.project\n        settings = replace(app.settings)\n        out_dir = qt_root(project.root) / \"PIC\"\n        general_top = int(config.get(\"general_top_y\", settings.start_y))\n        general_bottom = int(config.get(\"general_bottom_y\", 0))\n        margin = int(config.get(\"polygon_margin\", 0))\n        entry_left = int(config.get(\"entry_left_padding_x\", 0))\n        entry_right = int(config.get(\"entry_right_padding_x\", 0))\n        integrate_illustrations = bool(config.get(\"integrate_illustrations\", True))\n        specials = config.get(\"special_pages\", {}) if isinstance(config.get(\"special_pages\", {}), dict) else {}\n        workers = int(config.get(\"parallel_workers\", settings.crop_parallel_workers))\n\n        def job_builder(index: int, _position: int, _total: int):\n            page = project.images[index]\n            special = specials.get(page.stem, {}) if isinstance(specials.get(page.stem, {}), dict) else {}\n            top_y = int(special.get(\"top_y\", general_top))\n            bottom_y = int(special.get(\"bottom_y\", general_bottom))\n            return (\n                str(page), str(app._ppp_read_path(page)), str(out_dir), settings,\n                top_y, bottom_y, margin, str(pdic_path(page)), entry_left, entry_right, integrate_illustrations,\n                index,\n            )\n\n        def consume_result(_index: int, result):\n            records = list(getattr(result, \"records\", []) or [])\n            events = list(getattr(result, \"events\", []) or [])\n            append_crop_log(project.root, records)\n            append_illustration_crop_log(project.root, events)\n            return len(records)\n\n        def done(completed, total_pages, stopped, results, error):\n            if error is not None:\n                return\n            count = sum(int(v or 0) for v in results)\n            if stopped:\n                app.status_var.set(f\"插图切图已停止：完成 {completed}/{total_pages} 页，共导出 {count} 张\")\n            else:\n                app.status_var.set(f\"插图切图完成：{completed} 页，共 {count} 张\")\n\n        app._start_parallel_batch_task(\n            \"插图切图\", indices, split_illustrations_job, job_builder, consume_result, done,\n            item_label=lambda i: project.images[i].name,\n            max_workers=workers,\n        )\n\n'''
ctrl = ctrl.replace(insert_before, runner + insert_before, 1)
CTRL.write_text(ctrl, encoding="utf-8")


# 3) Extend the dedicated crop-controller tests to lock the Phase 4O runner seam.
test = TEST_CROP.read_text(encoding="utf-8")
assert "from pathlib import Path\n\nimport pytest\n" in test
test = test.replace(
    "from pathlib import Path\n\nimport pytest\n",
    "from dataclasses import dataclass\nfrom pathlib import Path\nfrom types import SimpleNamespace\n\nimport pytest\n",
    1,
)
insert_test_before = "def test_phase4n_app_wrapper_ui_binding_and_crop_runner_boundary_are_preserved() -> None:\n"
assert test.count(insert_test_before) == 1
runner_tests = '''@dataclass\nclass _RunnerSettings:\n    start_y: int = 17\n    crop_parallel_workers: int = 6\n\n\nclass _RunnerApp:\n    def __init__(self) -> None:\n        self._batch_active = False\n        self.project = SimpleNamespace(\n            root=Path(\"/project\"),\n            images=[Path(\"/pages/page001.png\"), Path(\"/pages/page002.png\")],\n        )\n        self.settings = _RunnerSettings()\n        self.status_var = _StatusVar()\n        self.ppp_reads: list[Path] = []\n        self.parallel: dict[str, object] | None = None\n\n    def _ppp_read_path(self, page: Path) -> Path:\n        self.ppp_reads.append(page)\n        return Path(\"/custom-ppp-read\") / f\"{page.stem}.ppp\"\n\n    def _start_parallel_batch_task(\n        self, title, items, worker, job_builder, consume_result, done, *, item_label, max_workers\n    ) -> bool:\n        self.parallel = {\n            \"title\": title,\n            \"items\": list(items),\n            \"worker\": worker,\n            \"job_builder\": job_builder,\n            \"consume_result\": consume_result,\n            \"done\": done,\n            \"item_label\": item_label,\n            \"max_workers\": max_workers,\n        }\n        return True\n\n\ndef test_phase4o_runner_preserves_no_project_and_batch_active_guards() -> None:\n    app = _RunnerApp()\n    app.project = None\n    IllustrationController(app)._start_illustration_crop([0], {})\n    assert app.parallel is None\n    assert app.status_var.values == []\n\n    app = _RunnerApp()\n    app._batch_active = True\n    IllustrationController(app)._start_illustration_crop([0], {})\n    assert app.parallel is None\n    assert app.status_var.values == [\"已有批量任务正在运行，未启动插图切图。\"]\n\n\ndef test_phase4o_runner_snapshots_settings_and_preserves_default_payload(monkeypatch) -> None:\n    app = _RunnerApp()\n    monkeypatch.setattr(illustration_module, \"qt_root\", lambda _root: Path(\"/qt-root\"))\n    monkeypatch.setattr(illustration_module, \"pdic_path\", lambda page: Path(\"/pdic\") / f\"{page.stem}.pdic\")\n\n    def fake_worker(*_args):\n        return None\n\n    monkeypatch.setattr(illustration_module, \"split_illustrations_job\", fake_worker)\n    IllustrationController(app)._start_illustration_crop([0, 1], {})\n\n    assert app.parallel is not None\n    assert app.parallel[\"title\"] == \"插图切图\"\n    assert app.parallel[\"items\"] == [0, 1]\n    assert app.parallel[\"worker\"] is fake_worker\n    assert app.parallel[\"max_workers\"] == 6\n    assert app.parallel[\"item_label\"](1) == \"page002.png\"\n\n    app.settings.start_y = 99\n    app.settings.crop_parallel_workers = 99\n    payload = app.parallel[\"job_builder\"](0, 1, 2)\n    assert payload == (\n        str(Path(\"/pages/page001.png\")),\n        str(Path(\"/custom-ppp-read/page001.ppp\")),\n        str(Path(\"/qt-root/PIC\")),\n        _RunnerSettings(start_y=17, crop_parallel_workers=6),\n        17, 0, 0,\n        str(Path(\"/pdic/page001.pdic\")),\n        0, 0, True, 0,\n    )\n    assert payload[3] is not app.settings\n    assert app.ppp_reads == [Path(\"/pages/page001.png\")]\n\n\ndef test_phase4o_runner_preserves_config_and_special_page_overrides(monkeypatch) -> None:\n    app = _RunnerApp()\n    monkeypatch.setattr(illustration_module, \"qt_root\", lambda _root: Path(\"/qt-root\"))\n    monkeypatch.setattr(illustration_module, \"pdic_path\", lambda page: Path(\"/pdic\") / f\"{page.stem}.pdic\")\n    config = {\n        \"general_top_y\": 11,\n        \"general_bottom_y\": 22,\n        \"polygon_margin\": 3,\n        \"entry_left_padding_x\": 4,\n        \"entry_right_padding_x\": 5,\n        \"integrate_illustrations\": False,\n        \"special_pages\": {\"page002\": {\"top_y\": 91, \"bottom_y\": 192}},\n        \"parallel_workers\": 7,\n    }\n    IllustrationController(app)._start_illustration_crop([0, 1], config)\n    assert app.parallel is not None\n    assert app.parallel[\"max_workers\"] == 7\n\n    general = app.parallel[\"job_builder\"](0, 1, 2)\n    special = app.parallel[\"job_builder\"](1, 2, 2)\n    assert general[4:12] == (11, 22, 3, str(Path(\"/pdic/page001.pdic\")), 4, 5, False, 0)\n    assert special[4:12] == (91, 192, 3, str(Path(\"/pdic/page002.pdic\")), 4, 5, False, 1)\n\n\ndef test_phase4o_runner_preserves_result_logging_and_counts(monkeypatch) -> None:\n    app = _RunnerApp()\n    crop_logs: list[tuple] = []\n    illustration_logs: list[tuple] = []\n    monkeypatch.setattr(\n        illustration_module, \"append_crop_log\",\n        lambda root, records: crop_logs.append((root, list(records))),\n    )\n    monkeypatch.setattr(\n        illustration_module, \"append_illustration_crop_log\",\n        lambda root, events: illustration_logs.append((root, list(events))),\n    )\n    IllustrationController(app)._start_illustration_crop([0], {})\n    assert app.parallel is not None\n    consume = app.parallel[\"consume_result\"]\n\n    result = SimpleNamespace(records=(\"r1\", \"r2\"), events=(\"e1\",))\n    assert consume(0, result) == 2\n    assert crop_logs == [(Path(\"/project\"), [\"r1\", \"r2\"])]\n    assert illustration_logs == [(Path(\"/project\"), [\"e1\"])]\n\n    assert consume(0, SimpleNamespace()) == 0\n    assert crop_logs[-1] == (Path(\"/project\"), [])\n    assert illustration_logs[-1] == (Path(\"/project\"), [])\n\n\ndef test_phase4o_runner_preserves_done_status_and_error_noop() -> None:\n    app = _RunnerApp()\n    IllustrationController(app)._start_illustration_crop([0], {})\n    assert app.parallel is not None\n    done = app.parallel[\"done\"]\n\n    done(1, 2, False, [4], RuntimeError(\"failed\"))\n    assert app.status_var.values == []\n\n    done(1, 2, True, [2, None, 3], None)\n    assert app.status_var.values[-1] == \"插图切图已停止：完成 1/2 页，共导出 5 张\"\n\n    done(2, 2, False, [1, 2], None)\n    assert app.status_var.values[-1] == \"插图切图完成：2 页，共 3 张\"\n\n\n'''
test = test.replace(insert_test_before, runner_tests + insert_test_before, 1)
test = test.replace(
    "def test_phase4n_app_wrapper_ui_binding_and_crop_runner_boundary_are_preserved() -> None:\n",
    "def test_phase4o_app_wrapper_ui_binding_and_crop_runner_boundary_are_preserved() -> None:\n",
    1,
)
old_asserts = '''    assert \"def _start_illustration_crop(self, indices: list[int], config: dict)\" in app\n    assert \"def split_illustrations_selected_scope(self) -> None:\" in controller\n    assert \"app._ppp_write_path(app.current_page)\" in controller\n    assert \"app._start_illustration_crop(indices, app._load_crop_settings())\" in controller\n    assert \"def _start_illustration_crop\" not in controller\n    assert \"split_illustrations_job\" not in controller\n'''
new_asserts = '''    assert (\n        \"def _start_illustration_crop(self, indices: list[int], config: dict) -> None:\\n\"\n        \"        self._illustration_controller_for_call()._start_illustration_crop(indices, config)\"\n    ) in app\n    assert \"def split_illustrations_selected_scope(self) -> None:\" in controller\n    assert \"app._ppp_write_path(app.current_page)\" in controller\n    assert \"app._start_illustration_crop(indices, app._load_crop_settings())\" in controller\n    assert \"def _start_illustration_crop(self, indices: list[int], config: dict)\" in controller\n    assert \"app._start_parallel_batch_task(\" in controller\n    assert \"def _start_parallel_batch_task\" not in controller\n    assert \"split_illustrations_job\" in controller\n    assert \"append_illustration_crop_log\" in controller\n    assert \"split_illustrations_job,\" not in app[: app.index(\"class PictureCaptureApp\")]\n    assert \"append_illustration_crop_log,\" not in app[: app.index(\"class PictureCaptureApp\")]\n'''
assert old_asserts in test
test = test.replace(old_asserts, new_asserts, 1)
TEST_CROP.write_text(test, encoding="utf-8")


# 4) Update the older illustration-controller boundary regression to the new seam.
test_ctrl = TEST_CTRL.read_text(encoding="utf-8")
assert "def test_phase4n_moves_only_illustration_crop_entry_and_preserves_runtime_boundary() -> None:\n" in test_ctrl
test_ctrl = test_ctrl.replace(
    "def test_phase4n_moves_only_illustration_crop_entry_and_preserves_runtime_boundary() -> None:\n",
    "def test_phase4o_moves_only_illustration_crop_runner_and_preserves_runtime_boundary() -> None:\n",
    1,
)
assert '    assert "def _start_illustration_crop" not in controller\n' in test_ctrl
assert '    assert "split_illustrations_job" not in controller\n' in test_ctrl
test_ctrl = test_ctrl.replace(
    '    assert "def _start_illustration_crop" not in controller\n',
    '    assert "def _start_illustration_crop" in controller\n',
    1,
)
test_ctrl = test_ctrl.replace(
    '    assert "split_illustrations_job" not in controller\n',
    '    assert "split_illustrations_job" in controller\n',
    1,
)
needle = '    assert "def _start_illustration_crop(self, indices: list[int], config: dict)" in app\n'
assert needle in test_ctrl
test_ctrl = test_ctrl.replace(
    needle,
    needle + '    assert "self._illustration_controller_for_call()._start_illustration_crop(indices, config)" in app\n',
    1,
)
TEST_CTRL.write_text(test_ctrl, encoding="utf-8")
