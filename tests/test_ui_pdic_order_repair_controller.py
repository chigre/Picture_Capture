from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from picture_capture.models import AppSettings, Entry
from picture_capture.ui.controllers import export as export_module
from picture_capture.ui.controllers.export import ExportController


class _Var:
    def __init__(self):
        self.values = []

    def set(self, value):
        self.values.append(value)


class _RepairApp:
    def __init__(self, root: Path, pages: list[Path]):
        self.project = SimpleNamespace(root=root, images=pages)
        self.current_page = pages[0] if pages else None
        self.image = object() if pages else None
        self._batch_active = False
        self.settings = AppSettings(columns=1, manual_x=0, column_width=100, gutter=0)
        self.status_var = _Var()
        self.current_index = 0
        self.batch = None
        self.selected = list(range(len(pages)))
        self.calls = []
        self.errors = []
        self.loaded = []

    def selected_page_indices(self):
        return list(self.selected)

    def _flush_deferred_page_save(self):
        self.calls.append("flush")

    def _sync_entry_editor_texts(self):
        self.calls.append("sync")

    def save_pdic(self, **kwargs):
        self.calls.append(("save", kwargs))

    def show_error(self, title, exc):
        self.errors.append((title, exc))

    def pages_tuple(self, index):
        pages = self.project.images
        return (
            pages[index].stem,
            pages[index - 1].stem if index > 0 else "@",
            pages[index + 1].stem if index + 1 < len(pages) else "@",
        )

    def load_page(self, index):
        self.loaded.append(index)

    def _start_batch_task(self, title, items, worker, done, **kwargs):
        self.batch = (title, list(items), worker, done, kwargs)
        return True


def _pages(tmp_path: Path, names=("001.jpg", "002.jpg")) -> list[Path]:
    result = []
    for name in names:
        page = tmp_path / name
        Image.new("RGB", (120, 200), "white").save(page)
        page.with_suffix(".pdic").write_text("placeholder\n", encoding="utf-8")
        result.append(page)
    return result


def test_repair_missing_project_keeps_exact_dialog(monkeypatch, tmp_path):
    shown = []
    monkeypatch.setattr(export_module.messagebox, "showinfo", lambda *a, **k: shown.append((a, k)))
    app = _RepairApp(tmp_path, [])
    app.project = None

    ExportController(app).repair_pdic_order_selected_scope()

    assert shown[0][0] == ("尚未打开", "请先打开包含扫描图片的项目目录。")
    assert shown[0][1]["parent"] is app


def test_repair_batch_active_keeps_exact_status(tmp_path):
    app = _RepairApp(tmp_path, _pages(tmp_path))
    app._batch_active = True

    ExportController(app).repair_pdic_order_selected_scope()

    assert app.status_var.values == ["已有批量任务正在运行，请结束后再修复排序。"]
    assert app.batch is None


def test_repair_range_error_and_empty_selection_contract(monkeypatch, tmp_path):
    pages = _pages(tmp_path)
    app = _RepairApp(tmp_path, pages)
    boom = ValueError("bad range")
    app.selected_page_indices = lambda: (_ for _ in ()).throw(boom)

    ExportController(app).repair_pdic_order_selected_scope()
    assert app.errors == [("页面范围错误", boom)]

    app.errors.clear()
    app.selected_page_indices = lambda: []
    ExportController(app).repair_pdic_order_selected_scope()
    assert app.status_var.values[-1] == "没有选中需要修复的页面"


def test_repair_preparation_and_no_existing_pdic_contract(monkeypatch, tmp_path):
    pages = _pages(tmp_path)
    for page in pages:
        page.with_suffix(".pdic").unlink()
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    app = _RepairApp(tmp_path, pages)

    ExportController(app).repair_pdic_order_selected_scope()

    assert app.status_var.values == ["所选范围没有已有 PDIC 文件"]
    assert app.calls == []


def test_repair_preserves_worker_sort_atomic_write_and_settings_reference(monkeypatch, tmp_path):
    pages = _pages(tmp_path)
    app = _RepairApp(tmp_path, pages)
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(export_module.messagebox, "askyesno", lambda *a, **k: True)
    entries_by_page = {
        pages[0]: [Entry("later", 10, 150), Entry("earlier", 10, 50)],
        pages[1]: [],
    }
    monkeypatch.setattr(export_module, "read_pdic", lambda path: list(entries_by_page[path.with_suffix(".jpg")]))
    seen_settings = []
    monkeypatch.setattr(
        export_module,
        "derive_nominal_geometry",
        lambda width, height, settings: seen_settings.append(settings) or (width, height),
    )
    monkeypatch.setattr(export_module, "read_page_sections", lambda page: [])
    monkeypatch.setattr(
        export_module,
        "sort_entries_column_y",
        lambda entries, geometry, sections: sorted(entries, key=lambda entry: entry.y),
    )
    writes = []
    monkeypatch.setattr(
        export_module,
        "write_pdic_atomic",
        lambda target, entries, width, meta: writes.append(
            (target, [(e.word, e.x, e.y) for e in entries], width, meta)
        ),
    )

    ExportController(app).repair_pdic_order_selected_scope()

    assert app.calls == [
        "flush",
        "sync",
        ("save", {"silent": True, "sync_editors": False}),
    ]
    assert app.batch is not None
    title, indices, worker, done, kwargs = app.batch
    assert title == "修复排序"
    assert indices == [0, 1]
    assert kwargs["item_label"](0) == "001.jpg"

    first = worker(0, 1, 2)
    second = worker(1, 2, 2)
    assert first == (0, 2, True)
    assert second == (1, 0, False)
    assert seen_settings == [app.settings]
    assert writes == [
        (
            pages[0].with_suffix(".pdic"),
            [("earlier", 10, 50), ("later", 10, 150)],
            120,
            ("001", "@", "002"),
        )
    ]

    done(2, 2, False, [first, second], None)
    assert app.loaded == [0]
    assert app.status_var.values[-1] == "修复排序完成：处理 2/2 页；实际改序 1 页；2 条记录"


def test_repair_stopped_status_and_error_done_are_unchanged(monkeypatch, tmp_path):
    pages = _pages(tmp_path, ("001.jpg",))
    app = _RepairApp(tmp_path, pages)
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(export_module.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(export_module, "read_pdic", lambda _path: [Entry("one", 10, 20)])
    monkeypatch.setattr(export_module, "derive_nominal_geometry", lambda *a: object())
    monkeypatch.setattr(export_module, "read_page_sections", lambda _page: [])
    monkeypatch.setattr(export_module, "sort_entries_column_y", lambda entries, *_a: entries)
    monkeypatch.setattr(export_module, "write_pdic_atomic", lambda *_a: None)

    ExportController(app).repair_pdic_order_selected_scope()
    _, _, worker, done, _ = app.batch
    result = worker(0, 1, 1)
    done(1, 1, True, [result], None)
    assert app.status_var.values[-1] == "修复排序已停止：处理 1/1 页；实际改序 0 页；1 条记录"

    before = list(app.status_var.values)
    done(0, 1, False, [], RuntimeError("failed"))
    assert app.status_var.values == before


def test_repair_wiring_is_app_wrapper_with_existing_ui_binding() -> None:
    root = Path(__file__).resolve().parents[1]
    app = (root / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller = (
        root / "src/picture_capture/ui/controllers/export.py"
    ).read_text(encoding="utf-8")
    start = app.index("    def repair_pdic_order_selected_scope(self) -> None:")
    end = app.index("    def export_picdic_index(self) -> None:", start)
    wrapper = app[start:end]
    assert "self._export_controller_for_call().repair_pdic_order_selected_scope()" in wrapper
    assert "_start_batch_task" not in wrapper
    assert "    def repair_pdic_order_selected_scope(self) -> None:" in controller
    assert 'settings = app.settings' in controller
    assert 'settings = replace(app.settings)' not in controller
    assert 'write_pdic_atomic(' in controller
    assert '("修复排序", self.repair_pdic_order_selected_scope)' in app
