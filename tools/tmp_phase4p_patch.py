from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/picture_capture/app.py"
EXPORT = ROOT / "src/picture_capture/ui/controllers/export.py"
TEST = ROOT / "tests/test_ui_export_controller.py"

app = APP.read_text(encoding="utf-8")
old_import = "from .picdic import PicDicBuildCancelled, build_picdic_package\n"
assert app.count(old_import) == 1, "unexpected PicDic import shape"
app = app.replace(old_import, "", 1)

old_build = '''    def build_picdic(self) -> None:\n        if not self.guard():\n            return\n        if self._batch_active:\n            self.status_var.set("已有批量任务正在运行，请结束后再制作 PicDic。")\n            return\n        try:\n            self.save_pdic(silent=True)\n        except Exception as exc:\n            self.show_error("PicDic 制作准备失败", exc)\n            return\n        root = self.project.root\n        language = self.settings.ocr_language\n\n        def worker(_item, _position: int, _total: int):\n            try:\n                return build_picdic_package(\n                    root, language, should_stop=self._batch_stop_event.is_set,\n                )\n            except PicDicBuildCancelled:\n                return None\n\n        def done(_completed, _total, stopped, results, error):\n            if error is not None or stopped or not results:\n                return\n            dsl, archive, words, images = results[-1]\n            self.status_var.set(f"PicDic 制作完成：{words} 个词头，{images} 张图片")\n            messagebox.showinfo(\n                "PicDic 制作完成",\n                f"词头：{words}\\n图片：{images}\\n\\nDSL：{dsl.name}\\n图片包：{archive.name}\\n目录：{dsl.parent}",\n                parent=self,\n            )\n\n        self._start_batch_task(\n            "PicDic 制作", [root], worker, done,\n            item_label=lambda _item: "生成 DSL 与图片包", refresh_page_quality=False,\n        )\n'''
new_build = '''    def build_picdic(self) -> None:\n        self._export_controller_for_call().build_picdic()\n'''
assert app.count(old_build) == 1, "build_picdic body drifted"
app = app.replace(old_build, new_build, 1)
APP.write_text(app, encoding="utf-8")

export = EXPORT.read_text(encoding="utf-8")
export = export.replace(
    '"""User-action orchestration for current-page OCR text import/export.\n',
    '"""User-action orchestration for text import/export and PicDic package builds.\n',
    1,
)
assert "from tkinter import messagebox\n" not in export
export = export.replace("from typing import Any\n", "from tkinter import messagebox\nfrom typing import Any\n", 1)
assert "from ...picdic import PicDicBuildCancelled, build_picdic_package\n" not in export
export = export.replace(
    "from ...processing import export_ocred, import_ocred\n",
    "from ...picdic import PicDicBuildCancelled, build_picdic_package\n"
    "from ...processing import export_ocred, import_ocred\n",
    1,
)
export = export.replace(
    '    """Coordinate current-page text import/export without owning file formats."""\n',
    '    """Coordinate stable export actions without owning persisted formats."""\n',
    1,
)
assert "    def build_picdic(self) -> None:\n" not in export
export += '''\n\n    def build_picdic(self) -> None:\n        app = self.app\n        if not app.guard():\n            return\n        if app._batch_active:\n            app.status_var.set("已有批量任务正在运行，请结束后再制作 PicDic。")\n            return\n        try:\n            app.save_pdic(silent=True)\n        except Exception as exc:\n            app.show_error("PicDic 制作准备失败", exc)\n            return\n        root = app.project.root\n        language = app.settings.ocr_language\n\n        def worker(_item, _position: int, _total: int):\n            try:\n                return build_picdic_package(\n                    root, language, should_stop=app._batch_stop_event.is_set,\n                )\n            except PicDicBuildCancelled:\n                return None\n\n        def done(_completed, _total, stopped, results, error):\n            if error is not None or stopped or not results:\n                return\n            dsl, archive, words, images = results[-1]\n            app.status_var.set(f"PicDic 制作完成：{words} 个词头，{images} 张图片")\n            messagebox.showinfo(\n                "PicDic 制作完成",\n                f"词头：{words}\\n图片：{images}\\n\\nDSL：{dsl.name}\\n图片包：{archive.name}\\n目录：{dsl.parent}",\n                parent=app,\n            )\n\n        app._start_batch_task(\n            "PicDic 制作", [root], worker, done,\n            item_label=lambda _item: "生成 DSL 与图片包", refresh_page_quality=False,\n        )\n'''
EXPORT.write_text(export, encoding="utf-8")

test = TEST.read_text(encoding="utf-8")
assert "class _PicDicApp:" not in test
addition = r'''

class _StopEvent:
    def __init__(self) -> None:
        self.value = False
        self.queries = 0

    def is_set(self) -> bool:
        self.queries += 1
        return self.value


class _PicDicApp:
    def __init__(self) -> None:
        self.project = SimpleNamespace(root=Path("/project"))
        self.settings = SimpleNamespace(ocr_language="ita")
        self.status_var = _StatusVar()
        self._batch_active = False
        self._batch_stop_event = _StopEvent()
        self.guard_result = True
        self.save_error: Exception | None = None
        self.calls: list[tuple] = []
        self.errors: list[tuple[str, Exception]] = []
        self.batch = None

    def guard(self) -> bool:
        self.calls.append(("guard",))
        return self.guard_result

    def save_pdic(self, silent: bool = False) -> None:
        self.calls.append(("save_pdic", silent))
        if self.save_error is not None:
            raise self.save_error

    def show_error(self, title: str, exc: Exception) -> None:
        self.errors.append((title, exc))

    def _start_batch_task(self, title, items, worker, done, **kwargs):
        self.calls.append(("start_batch", title, list(items), kwargs))
        self.batch = (title, list(items), worker, done, kwargs)
        return True


def test_build_picdic_guard_false_is_noop(monkeypatch) -> None:
    app = _PicDicApp()
    app.guard_result = False
    monkeypatch.setattr(
        export_module,
        "build_picdic_package",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not build")),
    )

    ExportController(app).build_picdic()

    assert app.calls == [("guard",)]
    assert app.status_var.values == []
    assert app.batch is None


def test_build_picdic_batch_active_preserves_exact_status_and_skips_save() -> None:
    app = _PicDicApp()
    app._batch_active = True

    ExportController(app).build_picdic()

    assert app.calls == [("guard",)]
    assert app.status_var.values == ["已有批量任务正在运行，请结束后再制作 PicDic。"]
    assert app.batch is None


def test_build_picdic_prepare_failure_uses_existing_error_contract() -> None:
    app = _PicDicApp()
    problem = OSError("cannot save")
    app.save_error = problem

    ExportController(app).build_picdic()

    assert app.calls == [("guard",), ("save_pdic", True)]
    assert app.errors == [("PicDic 制作准备失败", problem)]
    assert app.batch is None


def test_build_picdic_preserves_worker_batch_and_completion_contract(monkeypatch) -> None:
    app = _PicDicApp()
    built: list[tuple] = []
    dialogs: list[tuple] = []
    dsl = Path("/project/QT/PicDic/book.dsl")
    archive = Path("/project/QT/PicDic/book.dsl.files.zip")

    def fake_build(root, language, *, should_stop):
        built.append((root, language, should_stop))
        assert should_stop() is False
        return dsl, archive, 7, 9

    monkeypatch.setattr(export_module, "build_picdic_package", fake_build)
    monkeypatch.setattr(
        export_module.messagebox,
        "showinfo",
        lambda title, message, *, parent: dialogs.append((title, message, parent)),
    )

    ExportController(app).build_picdic()

    assert app.calls[0:2] == [("guard",), ("save_pdic", True)]
    assert app.batch is not None
    title, items, worker, done, kwargs = app.batch
    assert title == "PicDic 制作"
    assert items == [Path("/project")]
    assert kwargs["item_label"](Path("/project")) == "生成 DSL 与图片包"
    assert kwargs["refresh_page_quality"] is False
    result = worker(Path("/project"), 1, 1)
    assert result == (dsl, archive, 7, 9)
    assert built[0][0:2] == (Path("/project"), "ita")
    assert app._batch_stop_event.queries == 1

    done(1, 1, False, [result], None)

    assert app.status_var.values == ["PicDic 制作完成：7 个词头，9 张图片"]
    assert dialogs == [(
        "PicDic 制作完成",
        "词头：7\n图片：9\n\nDSL：book.dsl\n图片包：book.dsl.files.zip\n目录：/project/QT/PicDic",
        app,
    )]


def test_build_picdic_worker_keeps_cooperative_cancellation(monkeypatch) -> None:
    app = _PicDicApp()

    def cancel(*_args, **_kwargs):
        raise export_module.PicDicBuildCancelled()

    monkeypatch.setattr(export_module, "build_picdic_package", cancel)
    ExportController(app).build_picdic()
    assert app.batch is not None
    worker = app.batch[2]
    assert worker(Path("/project"), 1, 1) is None


def test_build_picdic_done_ignores_error_stop_and_empty_results(monkeypatch) -> None:
    app = _PicDicApp()
    dialogs: list[tuple] = []
    monkeypatch.setattr(
        export_module.messagebox,
        "showinfo",
        lambda *args, **kwargs: dialogs.append((args, kwargs)),
    )
    ExportController(app).build_picdic()
    assert app.batch is not None
    done = app.batch[3]

    done(0, 1, False, [], RuntimeError("failed"))
    done(0, 1, True, [(Path("a"), Path("b"), 1, 1)], None)
    done(0, 1, False, [], None)

    assert app.status_var.values == []
    assert dialogs == []


def test_build_picdic_wiring_moves_only_action_orchestration_to_export_controller() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller = (
        ROOT / "src/picture_capture/ui/controllers/export.py"
    ).read_text(encoding="utf-8")
    imports = app[: app.index("class PictureCaptureApp")]

    start = app.index("    def build_picdic(self) -> None:")
    end = app.index("    def _order_key(", start)
    block = app[start:end]
    assert "self._export_controller_for_call().build_picdic()" in block
    assert "build_picdic_package" not in block
    assert "PicDicBuildCancelled" not in block
    assert "from .picdic import PicDicBuildCancelled, build_picdic_package" not in imports
    assert "from ...picdic import PicDicBuildCancelled, build_picdic_package" in controller
    assert "    def build_picdic(self) -> None:" in controller
    assert '("PicDic制作", self.build_picdic)' in app
    assert "    def export_picdic_index(self) -> None:" in app
    assert "    def export_picdic_index(self) -> None:" not in controller
'''
TEST.write_text(test + addition, encoding="utf-8")
