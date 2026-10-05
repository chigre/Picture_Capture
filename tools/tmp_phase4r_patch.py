from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/picture_capture/app.py"
CONTROLLER = ROOT / "src/picture_capture/ui/controllers/export.py"
TESTS = ROOT / "tests/test_ui_export_controller.py"

app = APP.read_text(encoding="utf-8")
controller = CONTROLLER.read_text(encoding="utf-8")
tests = TESTS.read_text(encoding="utf-8")

method_start = "    def backup_pdic(self) -> None:\n"
next_method = "    def restore_from_pdic_backup(self) -> None:\n"
assert app.count(method_start) == 1
assert app.count(next_method) == 1
start = app.index(method_start)
end = app.index(next_method, start)
old_block = app[start:end]
for required in (
    'Stream every page PDIC into one timestamped backup without blocking Tk.',
    'self.status_var.set("已有批量任务正在运行，请结束后再备份PDIC。")',
    'self._flush_deferred_page_save()',
    'self._sync_entry_editor_texts()',
    'self.save_pdic(silent=True, sync_editors=False)',
    'messagebox.showinfo("备份PDIC", "当前项目没有可备份的 PDIC 文件。", parent=self)',
    'source.read_text(encoding="utf-8-sig").splitlines()',
    'os.replace(temp, target)',
    'self._start_batch_task(',
    'refresh_page_quality=False',
):
    assert required in old_block, required

wrapper = (
    "    def backup_pdic(self) -> None:\n"
    "        self._export_controller_for_call().backup_pdic()\n\n"
)
app = app[:start] + wrapper + app[end:]

assert "    def backup_pdic(self) -> None:" not in controller
backup_method = r'''

    def backup_pdic(self) -> None:
        """Stream every page PDIC into one timestamped backup without blocking Tk.

        Large projects can contain thousands of tiny PDIC files. Reading every
        file and joining all records on the Tk thread made the window appear
        frozen even though disk I/O was still progressing. The backup uses the
        existing sequential background-task runner and writes each page directly
        to a temporary output stream. No page image pixels are read and the full
        backup is never accumulated in memory.
        """
        app = self.app
        if not app.project or not app.current_page or app.image is None:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=app)
            return
        if app._batch_active:
            app.status_var.set("已有批量任务正在运行，请结束后再备份PDIC。")
            return
        try:
            app._flush_deferred_page_save()
            app._sync_entry_editor_texts()
            app.save_pdic(silent=True, sync_editors=False)
        except Exception as exc:
            app.show_error("备份PDIC失败", exc)
            return

        project = app.project
        pages = [page for page in project.images if pdic_path(page).exists()]
        if not pages:
            messagebox.showinfo("备份PDIC", "当前项目没有可备份的 PDIC 文件。", parent=app)
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = exports_root(project.root) / f"all_pdic_backup_{stamp}.txt"
        temp = target.with_name(f".{target.name}.tmp")
        state: dict[str, object] = {"stream": None, "page_count": 0, "record_count": 0}

        def worker(page: Path, _position: int, _total: int):
            stream = state.get("stream")
            if stream is None:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                stream = temp.open("w", encoding="utf-8", newline="\n")
                state["stream"] = stream
            source = pdic_path(page)
            # Keep only one page in memory at a time. This is substantially
            # faster than per-line writes on Windows/network disks while still
            # avoiding the old project-wide list/join memory spike.
            page_lines = [
                raw for raw in source.read_text(encoding="utf-8-sig").splitlines()
                if raw.strip()
            ]
            count = len(page_lines)
            if count:
                stream.write("\n".join(page_lines))
                stream.write("\n")
                state["page_count"] = int(state.get("page_count", 0)) + 1
                state["record_count"] = int(state.get("record_count", 0)) + count
            return count

        def done(completed: int, total: int, stopped: bool, _results, error) -> None:
            stream = state.get("stream")
            if stream is not None:
                try:
                    stream.flush()
                    stream.close()
                except OSError:
                    pass
                state["stream"] = None
            if error is not None or stopped:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                if error is None:
                    app.status_var.set(
                        f"PDIC备份已停止：完成 {completed}/{total} 页，未生成不完整备份。"
                    )
                return
            try:
                if not temp.exists():
                    temp.write_text("", encoding="utf-8")
                os.replace(temp, target)
                page_count = int(state.get("page_count", 0))
                record_count = int(state.get("record_count", 0))
                app.status_var.set(
                    f"PDIC备份完成：{target.name}｜{page_count} 页｜{record_count} 条"
                )
                messagebox.showinfo(
                    "备份PDIC",
                    f"已生成：\n{target}\n\n包含 {page_count} 个有记录页面，共 {record_count} 条 PDIC。",
                    parent=app,
                )
            except Exception as exc:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                app.show_error("备份PDIC失败", exc)

        app._start_batch_task(
            "备份PDIC", pages, worker, done, item_label=lambda page: page.name,
            refresh_page_quality=False,
        )
'''
controller = controller.rstrip() + backup_method + "\n"

extra_tests = r'''


def _prepare_backup_files(tmp_path: Path, names=("001.jpg", "002.jpg")):
    pages = [tmp_path / name for name in names]
    for page in pages:
        page.with_suffix(".pdic").write_text("placeholder", encoding="utf-8")
    return pages


def test_backup_pdic_missing_project_contract(monkeypatch, tmp_path) -> None:
    app = _IndexApp(tmp_path, [])
    app.project = None
    dialogs: list[tuple] = []
    monkeypatch.setattr(
        export_module.messagebox, "showinfo",
        lambda title, message, *, parent: dialogs.append((title, message, parent)),
    )

    ExportController(app).backup_pdic()

    assert dialogs == [("尚未打开", "请先打开包含扫描图片的项目目录。", app)]
    assert app.calls == []
    assert app.batch is None


def test_backup_pdic_batch_active_preserves_exact_status(tmp_path) -> None:
    pages = _prepare_backup_files(tmp_path, ("001.jpg",))
    app = _IndexApp(tmp_path, pages)
    app._batch_active = True

    ExportController(app).backup_pdic()

    assert app.status_var.values == ["已有批量任务正在运行，请结束后再备份PDIC。"]
    assert app.calls == []
    assert app.batch is None


def test_backup_pdic_prepare_failure_preserves_error_contract(tmp_path) -> None:
    pages = _prepare_backup_files(tmp_path, ("001.jpg",))
    app = _IndexApp(tmp_path, pages)
    problem = OSError("save failed")
    app.save_error = problem

    ExportController(app).backup_pdic()

    assert app.calls == [("flush",), ("sync",), ("save_pdic", True, False)]
    assert app.errors == [("备份PDIC失败", problem)]
    assert app.batch is None


def test_backup_pdic_no_saved_pdic_shows_existing_info(monkeypatch, tmp_path) -> None:
    pages = [tmp_path / "001.jpg"]
    app = _IndexApp(tmp_path, pages)
    dialogs: list[tuple] = []
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(
        export_module.messagebox, "showinfo",
        lambda title, message, *, parent: dialogs.append((title, message, parent)),
    )

    ExportController(app).backup_pdic()

    assert app.calls == [("flush",), ("sync",), ("save_pdic", True, False)]
    assert dialogs == [("备份PDIC", "当前项目没有可备份的 PDIC 文件。", app)]
    assert app.batch is None


def test_backup_pdic_streams_filters_blank_lines_and_atomically_publishes(monkeypatch, tmp_path) -> None:
    pages = _prepare_backup_files(tmp_path)
    pages[0].with_suffix(".pdic").write_text("\ufeffuno\n\n due \n", encoding="utf-8")
    pages[1].with_suffix(".pdic").write_text("\n\ntre\n", encoding="utf-8")
    app = _IndexApp(tmp_path, pages)
    output = tmp_path / "output"
    output.mkdir()
    dialogs: list[tuple] = []
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(export_module, "exports_root", lambda _root: output)
    monkeypatch.setattr(
        export_module.messagebox, "showinfo",
        lambda title, message, *, parent: dialogs.append((title, message, parent)),
    )

    ExportController(app).backup_pdic()

    assert app.calls[:3] == [("flush",), ("sync",), ("save_pdic", True, False)]
    assert app.batch is not None
    title, items, worker, done, kwargs = app.batch
    assert title == "备份PDIC"
    assert items == pages
    assert kwargs["item_label"](pages[0]) == "001.jpg"
    assert kwargs["refresh_page_quality"] is False
    assert list(output.iterdir()) == []

    assert worker(pages[0], 1, 2) == 2
    assert worker(pages[1], 2, 2) == 1
    temps = list(output.glob(".all_pdic_backup_*.txt.tmp"))
    assert len(temps) == 1
    done(2, 2, False, [2, 1], None)

    assert not list(output.glob(".*.tmp"))
    targets = list(output.glob("all_pdic_backup_*.txt"))
    assert len(targets) == 1
    assert targets[0].read_text(encoding="utf-8") == "uno\n due \ntre\n"
    assert app.status_var.values == [
        f"PDIC备份完成：{targets[0].name}｜2 页｜3 条"
    ]
    assert dialogs == [(
        "备份PDIC",
        f"已生成：\n{targets[0]}\n\n包含 2 个有记录页面，共 3 条 PDIC。",
        app,
    )]


def test_backup_pdic_stop_removes_temp_and_never_publishes_partial_output(monkeypatch, tmp_path) -> None:
    pages = _prepare_backup_files(tmp_path, ("001.jpg",))
    pages[0].with_suffix(".pdic").write_text("word\n", encoding="utf-8")
    app = _IndexApp(tmp_path, pages)
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(export_module, "exports_root", lambda _root: output)

    ExportController(app).backup_pdic()
    assert app.batch is not None
    _, _, worker, done, _ = app.batch
    assert worker(pages[0], 1, 1) == 1
    assert list(output.glob(".all_pdic_backup_*.txt.tmp"))

    done(1, 1, True, [1], None)

    assert not list(output.glob(".*.tmp"))
    assert not list(output.glob("all_pdic_backup_*.txt"))
    assert app.status_var.values == [
        "PDIC备份已停止：完成 1/1 页，未生成不完整备份。"
    ]


def test_backup_pdic_error_removes_temp_without_success_status(monkeypatch, tmp_path) -> None:
    pages = _prepare_backup_files(tmp_path, ("001.jpg",))
    pages[0].with_suffix(".pdic").write_text("word\n", encoding="utf-8")
    app = _IndexApp(tmp_path, pages)
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(export_module, "exports_root", lambda _root: output)

    ExportController(app).backup_pdic()
    assert app.batch is not None
    _, _, worker, done, _ = app.batch
    assert worker(pages[0], 1, 1) == 1

    done(0, 1, False, [], RuntimeError("failed"))

    assert not list(output.glob(".*.tmp"))
    assert not list(output.glob("all_pdic_backup_*.txt"))
    assert app.status_var.values == []


def test_backup_pdic_wiring_keeps_restore_outside_phase4r() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller = (
        ROOT / "src/picture_capture/ui/controllers/export.py"
    ).read_text(encoding="utf-8")

    start = app.index("    def backup_pdic(self) -> None:")
    end = app.index("    def restore_from_pdic_backup(self) -> None:", start)
    block = app[start:end]
    assert "self._export_controller_for_call().backup_pdic()" in block
    assert "_start_batch_task" not in block
    assert "    def backup_pdic(self) -> None:" in controller
    assert "    def restore_from_pdic_backup(self) -> None:" in app
    assert "    def restore_from_pdic_backup(self) -> None:" not in controller
    assert '"备份PDIC"' in app and "self.backup_pdic" in app
'''

tests = tests.rstrip() + extra_tests + "\n"

APP.write_text(app, encoding="utf-8")
CONTROLLER.write_text(controller, encoding="utf-8")
TESTS.write_text(tests, encoding="utf-8")
