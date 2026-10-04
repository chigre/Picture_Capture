from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import picture_capture.ui.controllers.illustration as illustration_module
from picture_capture.ui.controllers.illustration import IllustrationController


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class _Settings:
    marker: int = 7


class _StatusVar:
    def __init__(self) -> None:
        self.values: list[str] = []

    def set(self, value: str) -> None:
        self.values.append(value)


class _BoolVar:
    def __init__(self) -> None:
        self.values: list[bool] = []

    def set(self, value: bool) -> None:
        self.values.append(bool(value))


class _App:
    def __init__(self) -> None:
        self._batch_active = False
        self.project = SimpleNamespace(
            root=Path("/project"),
            images=[Path("/pages/page001.png"), Path("/pages/page002.png")],
        )
        self.current_page = Path("/pages/page001.png")
        self.current_index = 0
        self.image = object()
        self.polygons = ["manual-polygon"]
        self.settings = _Settings()
        self.status_var = _StatusVar()
        self.polygon_var = _BoolVar()
        self.indices: list[int] = [0, 1]
        self.range_error: Exception | None = None
        self.calls: list[tuple] = []
        self.errors: list[tuple[str, Exception]] = []
        self.batch: dict[str, object] | None = None

    def selected_page_indices(self) -> list[int]:
        self.calls.append(("selected_page_indices",))
        if self.range_error is not None:
            raise self.range_error
        return list(self.indices)

    def show_error(self, title: str, exc: Exception) -> None:
        self.calls.append(("show_error", title, exc))
        self.errors.append((title, exc))

    def _ppp_write_path(self, page: Path) -> Path:
        self.calls.append(("ppp_write_path", page))
        return Path("/ppp-write") / f"{page.stem}.ppp"

    def _ppp_read_path(self, page: Path) -> Path:
        self.calls.append(("ppp_read_path", page))
        return Path("/ppp-read") / f"{page.stem}.ppp"

    def _update_page_row(self, index: int) -> None:
        self.calls.append(("update_page_row", index))

    def redraw(self) -> None:
        self.calls.append(("redraw",))

    def _start_batch_task(
        self,
        title,
        items,
        worker,
        done,
        *,
        item_label,
        foreground_page_edit=False,
        page_indexer=None,
        **_kwargs,
    ) -> bool:
        self.calls.append(("start_batch", title, list(items), foreground_page_edit))
        self.batch = {
            "title": title,
            "items": list(items),
            "worker": worker,
            "done": done,
            "item_label": item_label,
            "foreground_page_edit": foreground_page_edit,
            "page_indexer": page_indexer,
        }
        return True


def _stub_dialogs(monkeypatch, *, confirm: bool = True):
    infos: list[tuple] = []
    confirms: list[tuple] = []

    def showinfo(title, text, *, parent=None):
        infos.append((title, text, parent))

    def askyesno(title, text, *, parent=None):
        confirms.append((title, text, parent))
        return confirm

    monkeypatch.setattr(illustration_module.messagebox, "showinfo", showinfo)
    monkeypatch.setattr(illustration_module.messagebox, "askyesno", askyesno)
    return infos, confirms


def test_batch_active_short_circuits_before_project_checks(monkeypatch) -> None:
    app = _App()
    app._batch_active = True
    infos, confirms = _stub_dialogs(monkeypatch)

    IllustrationController(app).detect_illustrations_selected_scope()

    assert app.status_var.values == ["已有批量任务正在运行，请结束后再执行插图识别。"]
    assert app.calls == []
    assert infos == []
    assert confirms == []


def test_missing_foreground_state_shows_original_info_dialog(monkeypatch) -> None:
    app = _App()
    app.image = None
    infos, confirms = _stub_dialogs(monkeypatch)

    IllustrationController(app).detect_illustrations_selected_scope()

    assert infos == [("尚未打开", "请先打开包含扫描图片的项目目录。", app)]
    assert confirms == []
    assert app.calls == []


def test_invalid_and_empty_ranges_preserve_original_behavior(monkeypatch) -> None:
    app = _App()
    problem = ValueError("bad range")
    app.range_error = problem
    _stub_dialogs(monkeypatch)

    IllustrationController(app).detect_illustrations_selected_scope()

    assert app.calls == [
        ("selected_page_indices",),
        ("show_error", "页面范围无效", problem),
    ]
    assert app.errors == [("页面范围无效", problem)]
    assert app.batch is None

    app = _App()
    app.indices = []
    infos, confirms = _stub_dialogs(monkeypatch)

    IllustrationController(app).detect_illustrations_selected_scope()

    assert app.calls == [("selected_page_indices",)]
    assert infos == []
    assert confirms == []
    assert app.batch is None


def test_foreground_ppp_is_saved_before_confirmation_and_cancel_stops(monkeypatch) -> None:
    app = _App()
    events: list[tuple] = []
    _infos, confirms = _stub_dialogs(monkeypatch, confirm=False)

    def fake_write(path, polygons, stem):
        events.append(("write_ppp", path, list(polygons), stem))

    monkeypatch.setattr(illustration_module, "write_ppp", fake_write)

    IllustrationController(app).detect_illustrations_selected_scope()

    assert app.calls == [
        ("selected_page_indices",),
        ("ppp_write_path", Path("/pages/page001.png")),
    ]
    assert events == [
        ("write_ppp", Path("/ppp-write/page001.ppp"), ["manual-polygon"], "page001"),
    ]
    assert len(confirms) == 1
    assert confirms[0][0] == "插图识别"
    assert "page001.png → page002.png（共 2 页）" in confirms[0][1]
    assert confirms[0][2] is app
    assert app.batch is None


def test_confirmed_action_snapshots_settings_and_starts_original_batch(monkeypatch) -> None:
    app = _App()
    _stub_dialogs(monkeypatch, confirm=True)
    monkeypatch.setattr(illustration_module, "write_ppp", lambda *_args: None)

    IllustrationController(app).detect_illustrations_selected_scope()

    assert app.batch is not None
    assert app.batch["title"] == "插图识别"
    assert app.batch["items"] == [0, 1]
    assert app.batch["foreground_page_edit"] is True
    assert app.batch["item_label"](1) == "page002.png"
    assert app.batch["page_indexer"](1) == 1
    assert app.calls[-1] == ("start_batch", "插图识别", [0, 1], True)


def test_worker_uses_settings_snapshot_and_detection_job(monkeypatch) -> None:
    app = _App()
    _stub_dialogs(monkeypatch, confirm=True)
    monkeypatch.setattr(illustration_module, "write_ppp", lambda *_args: None)
    captured: list[tuple] = []

    def fake_detect(page, settings, index):
        captured.append((page, settings, index))
        return {"auto": 2}

    monkeypatch.setattr(illustration_module, "detect_illustrations_job", fake_detect)

    IllustrationController(app).detect_illustrations_selected_scope()
    assert app.batch is not None
    app.settings.marker = 99

    result = app.batch["worker"](1, 2, 2)

    assert result == {"auto": 2}
    assert captured == [
        (str(Path("/pages/page002.png")), _Settings(marker=7), 1),
    ]
    assert captured[0][1] is not app.settings


def test_done_preserves_status_reload_update_toggle_and_redraw(monkeypatch) -> None:
    app = _App()
    _stub_dialogs(monkeypatch, confirm=True)
    monkeypatch.setattr(illustration_module, "write_ppp", lambda *_args: None)
    reads: list[Path] = []

    def fake_read(path: Path):
        reads.append(path)
        return ["reloaded"]

    monkeypatch.setattr(illustration_module, "read_ppp", fake_read)

    IllustrationController(app).detect_illustrations_selected_scope()
    assert app.batch is not None
    done = app.batch["done"]

    app.calls.clear()
    done(2, 2, False, [{"auto": 2}, {"auto": 3}], None)

    assert app.status_var.values[-1] == "插图识别完成：2 页，自动识别 5 个插图区域；人工 PPP 已保留"
    assert reads == [Path("/ppp-read/page001.ppp")]
    assert app.polygons == ["reloaded"]
    assert app.calls == [
        ("ppp_read_path", Path("/pages/page001.png")),
        ("update_page_row", 0),
        ("redraw",),
    ]
    assert app.polygon_var.values == [True]

    app.status_var.values.clear()
    app.calls.clear()
    app.polygon_var.values.clear()
    done(1, 2, True, [{"auto": 4}], None)
    assert app.status_var.values == ["插图识别已停止：完成 1/2 页，自动识别 4 个插图区域"]
    assert app.polygon_var.values == [True]

    app.status_var.values.clear()
    app.calls.clear()
    app.polygon_var.values.clear()
    done(1, 2, False, [{"auto": 4}], RuntimeError("failed"))
    assert app.status_var.values == []
    assert app.calls == []
    assert app.polygon_var.values == []


def test_done_does_not_reload_when_current_page_is_outside_selected_range(monkeypatch) -> None:
    app = _App()
    app.indices = [1]
    _stub_dialogs(monkeypatch, confirm=True)
    monkeypatch.setattr(illustration_module, "write_ppp", lambda *_args: None)
    monkeypatch.setattr(
        illustration_module,
        "read_ppp",
        lambda _path: (_ for _ in ()).throw(AssertionError("must not reload")),
    )

    IllustrationController(app).detect_illustrations_selected_scope()
    assert app.batch is not None
    app.calls.clear()
    app.batch["done"](1, 1, False, [{"auto": 1}], None)

    assert app.status_var.values[-1] == "插图识别完成：1 页，自动识别 1 个插图区域；人工 PPP 已保留"
    assert app.calls == []
    assert app.polygon_var.values == []


def test_illustration_controller_has_no_reverse_dependency_on_app_module() -> None:
    path = ROOT / "src/picture_capture/ui/controllers/illustration.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_illustration_controller_wiring_preserves_app_compatibility_method() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controllers = (
        ROOT / "src/picture_capture/ui/controllers/__init__.py"
    ).read_text(encoding="utf-8")

    imports = app[: app.index("class PictureCaptureApp")]
    assert "IllustrationController" in imports
    assert "self.illustration_controller = IllustrationController(self)" in app
    assert app.index("self.illustration_controller = IllustrationController(self)") < app.index("self._build_ui()")
    assert "def _illustration_controller_for_call(" in app
    assert 'self.__dict__.get("illustration_controller")' in app
    assert "def detect_illustrations_selected_scope(self)" in app
    assert "self._illustration_controller_for_call().detect_illustrations_selected_scope()" in app
    assert "from .illustration import IllustrationController" in controllers
    assert '"IllustrationController"' in controllers



def test_phase4n_moves_only_illustration_crop_entry_and_preserves_runtime_boundary() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller = (
        ROOT / "src/picture_capture/ui/controllers/illustration.py"
    ).read_text(encoding="utf-8")
    runtime = (
        ROOT / "src/picture_capture/postproduction_single_line_runtime.py"
    ).read_text(encoding="utf-8")

    assert "def split_illustrations_selected_scope(self)" in app
    assert "self._illustration_controller_for_call().split_illustrations_selected_scope()" in app
    assert "def _start_illustration_crop(self, indices: list[int], config: dict)" in app
    assert "def split_illustrations_selected_scope(self)" in controller
    assert "def _start_illustration_crop" not in controller
    assert "split_illustrations_job" not in controller
    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" in runtime
    assert "detect_illustrations_selected_scope" not in runtime
    assert "split_illustrations_selected_scope" not in runtime
