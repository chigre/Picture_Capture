from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import picture_capture.ui.controllers.headword as headword_module
from picture_capture.models import AppSettings, Entry
from picture_capture.ui.controllers.headword import HeadwordController


ROOT = Path(__file__).resolve().parents[1]


class _Var:
    def __init__(self) -> None:
        self.values: list[str] = []

    def set(self, value: str) -> None:
        self.values.append(value)


class _SelectionApp:
    def __init__(self, root: Path) -> None:
        self.project = SimpleNamespace(root=root)
        self._batch_active = False
        self._word_fill_source_path: Path | None = None
        self._word_fill_source_signature = None
        self._word_fill_source_mapping = None
        self._word_fill_source_present_pages = None
        self.status_var = _Var()
        self.errors: list[tuple[str, Exception]] = []

    def show_error(self, title: str, exc: Exception) -> None:
        self.errors.append((title, exc))


def _controller(app) -> HeadwordController:
    return HeadwordController(
        app,
        parse_words_of_pages_text=lambda *_args, **_kwargs: {},
        fill_page_entries=lambda entries, words: (0, len(entries), len(words)),
    )


def test_headword_controller_has_no_reverse_dependency_on_app_module() -> None:
    path = ROOT / "src/picture_capture/ui/controllers/headword.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_select_headword_source_preserves_cached_mapping_for_unchanged_file(
    tmp_path, monkeypatch,
) -> None:
    source = tmp_path / "_WordsOfPages.txt"
    source.write_text("001\talpha\n", encoding="utf-8")
    app = _SelectionApp(tmp_path)
    controller = _controller(app)
    signature = controller._file_signature(source)
    cached_mapping = {"001": ["alpha"]}
    cached_present = {"001"}
    app._word_fill_source_path = source
    app._word_fill_source_signature = signature
    app._word_fill_source_mapping = cached_mapping
    app._word_fill_source_present_pages = cached_present
    monkeypatch.setattr(
        headword_module.filedialog, "askopenfilename", lambda **_kwargs: str(source),
    )

    controller.select_existing_headwords_file()

    assert app._word_fill_source_mapping is cached_mapping
    assert app._word_fill_source_present_pages is cached_present
    assert app._word_fill_source_signature == signature
    assert app.status_var.values[-1] == (
        "已选择词条文件：_WordsOfPages.txt（已缓存解析结果）；调整页面范围后点击[填充词条]。"
    )
    assert app.errors == []


def test_select_headword_source_invalidates_cache_when_signature_changes(
    tmp_path, monkeypatch,
) -> None:
    source = tmp_path / "new.txt"
    source.write_text("001\talpha\n", encoding="utf-8")
    app = _SelectionApp(tmp_path)
    app._word_fill_source_signature = ("old", 1, 1)
    app._word_fill_source_mapping = {"old": ["value"]}
    app._word_fill_source_present_pages = {"old"}
    monkeypatch.setattr(
        headword_module.filedialog, "askopenfilename", lambda **_kwargs: str(source),
    )

    _controller(app).select_existing_headwords_file()

    assert app._word_fill_source_path == source
    assert app._word_fill_source_mapping is None
    assert app._word_fill_source_present_pages is None
    assert app.status_var.values[-1] == (
        "已选择词条文件：new.txt；调整页面范围后点击[填充词条]。"
    )


class _FillApp:
    def __init__(self, root: Path, page: Path, source: Path) -> None:
        self.project = SimpleNamespace(root=root, images=[page])
        self.current_page = page
        self.current_index = 0
        self.image = object()
        self.settings = AppSettings()
        self._batch_active = False
        self._word_fill_source_path = source
        self._word_fill_source_signature = HeadwordController._file_signature(source)
        self._word_fill_source_mapping = None
        self._word_fill_source_present_pages = None
        self.status_var = _Var()
        self.batch_text_var = _Var()
        self.calls: list[tuple] = []
        self.errors: list[tuple[str, Exception]] = []
        self.batch = None
        self.fill_checks: list[tuple] = []

    def selected_page_indices(self) -> list[int]:
        return [0]

    def _flush_deferred_page_save(self) -> None:
        self.calls.append(("flush",))

    def _sync_entry_editor_texts(self) -> None:
        self.calls.append(("sync",))

    def save_pdic(self, *, silent: bool, sync_editors: bool) -> None:
        self.calls.append(("save_pdic", silent, sync_editors))

    def show_error(self, title: str, exc: Exception) -> None:
        self.errors.append((title, exc))

    def _start_batch_task(self, title, items, worker, done, **kwargs):
        self.batch = (title, list(items), worker, done, kwargs)
        return True

    def _record_word_fill_check(self, *args, **kwargs) -> None:
        self.fill_checks.append((args, kwargs))

    def _persist_word_fill_status(self) -> None:
        self.calls.append(("persist_fill_status",))

    def load_page(self, index: int) -> None:
        self.calls.append(("load_page", index))


def test_fill_headwords_keeps_parse_cache_local_until_done(tmp_path, monkeypatch) -> None:
    page = tmp_path / "001.png"
    Image.new("RGB", (80, 120), "white").save(page)
    source = tmp_path / "_WordsOfPages.txt"
    source.write_text("001\talpha\n", encoding="utf-8")
    app = _FillApp(tmp_path, page, source)
    entries = [Entry(word="", x=4, y=10)]
    writes: list[tuple] = []

    monkeypatch.setattr(headword_module, "read_pdic", lambda _path: entries)
    monkeypatch.setattr(
        headword_module,
        "sort_entries_reading_order",
        lambda rows, _geometry, _sections: rows,
    )
    monkeypatch.setattr(headword_module, "derive_nominal_geometry", lambda *_args: object())
    monkeypatch.setattr(headword_module, "read_page_sections", lambda _page: [])
    monkeypatch.setattr(
        headword_module,
        "write_pdic",
        lambda path, rows, width, pages: writes.append(
            (path, [row.word for row in rows], width, pages)
        ),
    )

    parse_calls: list[tuple[str, tuple[str, ...]]] = []

    def parse_source(text: str, stems: list[str], *, present_pages: set[str] | None = None):
        parse_calls.append((text, tuple(stems)))
        assert present_pages is not None
        present_pages.add("001")
        return {"001": ["alpha"]}

    def fill_rows(rows, words):
        rows[0].word = words[0]
        return 1, len(rows), len(words)

    controller = HeadwordController(
        app,
        parse_words_of_pages_text=parse_source,
        fill_page_entries=fill_rows,
    )
    controller.fill_existing_headwords()

    assert app.calls[:3] == [("flush",), ("sync",), ("save_pdic", True, False)]
    assert app.batch is not None
    title, items, worker, done, kwargs = app.batch
    assert title == "填充词条"
    assert items == [0]
    assert kwargs["foreground_page_edit"] is False
    assert app._word_fill_source_mapping is None
    assert app.batch_text_var.values[-1] == "填充词条：准备读取并解析词条文件 0/1"

    result = worker(0, 1, 1)

    assert result == {
        "index": 0,
        "filled": 1,
        "line_count": 1,
        "word_count": 1,
        "has_data": True,
        "mismatch": False,
    }
    assert len(parse_calls) == 1
    assert parse_calls[0][0].splitlines() == ["001\talpha"]
    assert parse_calls[0][1] == ("001",)
    assert app._word_fill_source_mapping is None
    assert writes and writes[0][1] == ["alpha"]

    done(1, 1, False, [result], None)

    assert app._word_fill_source_mapping == {"001": ["alpha"]}
    assert app._word_fill_source_present_pages == {"001"}
    assert len(app.fill_checks) == 1
    assert ("persist_fill_status",) in app.calls
    assert ("load_page", 0) in app.calls
    assert app.status_var.values[-1] == (
        "既有词条填充完成：1/1 页，填入 1 个词条；数量不一致 0 页"
        "（填充状态格淡红提示），无资料 0 页；来源：_WordsOfPages.txt"
    )
    assert app.errors == []


def test_headword_controller_wiring_preserves_app_compatibility_methods() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controllers = (
        ROOT / "src/picture_capture/ui/controllers/__init__.py"
    ).read_text(encoding="utf-8")
    controller = (
        ROOT / "src/picture_capture/ui/controllers/headword.py"
    ).read_text(encoding="utf-8")

    imports = app[: app.index("class PictureCaptureApp")]
    assert "HeadwordController" in imports
    assert "self.headword_controller = HeadwordController(" in app
    assert app.index("self.headword_controller = HeadwordController(") < app.index("self._build_ui()")
    assert "def _headword_controller_for_call(" in app
    assert 'self.__dict__.get("headword_controller")' in app
    assert "def select_existing_headwords_file(self)" in app
    assert (
        "self._headword_controller_for_call().select_existing_headwords_file()" in app
    )
    assert "def fill_existing_headwords(self)" in app
    assert "self._headword_controller_for_call().fill_existing_headwords()" in app
    assert "from .headword import HeadwordController" in controllers
    assert '"HeadwordController"' in controllers
    assert "class HeadwordController" in controller
