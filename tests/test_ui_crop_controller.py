from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import picture_capture.ui.controllers.crop as crop_module
from picture_capture.ui.controllers.crop import CropController


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class _Entry:
    word: str


@dataclass
class _Settings:
    marker: int = 1
    start_y: int = 11


class _StatusVar:
    def __init__(self) -> None:
        self.values: list[str] = []

    def set(self, value: str) -> None:
        self.values.append(value)


class _App:
    def __init__(self) -> None:
        self._batch_active = False
        self.project = SimpleNamespace(
            root=Path("/project"),
            images=[Path("/pages/page001.png"), Path("/pages/page002.png")],
        )
        self.current_page = Path("/pages/page001.png")
        self.current_index = 2
        self.entries = [_Entry("one"), _Entry("two")]
        self.polygons = ["poly-a", "poly-b"]
        self.settings = _Settings(marker=7)
        self.crop_config = {
            "general_top_y": 13,
            "general_bottom_y": 777,
            "entry_left_padding_x": 4,
            "entry_right_padding_x": 7,
            "integrate_illustrations": False,
            "special_pages": {
                "page001": {"top_y": 23, "bottom_y": 456},
            },
        }
        self.status_var = _StatusVar()
        self.guard_result = True
        self.geometry_result = True
        self.calls: list[tuple] = []
        self.batch: dict[str, object] | None = None

    def guard(self) -> bool:
        self.calls.append(("guard",))
        return self.guard_result

    def _guard_transformed_geometry(self, action: str) -> bool:
        self.calls.append(("guard_geometry", action))
        return self.geometry_result

    def _load_crop_settings(self):
        self.calls.append(("load_crop_settings",))
        return self.crop_config

    def _start_batch_task(self, label, items, worker, done, *, item_label) -> None:
        self.calls.append(("start_batch", label, list(items)))
        self.batch = {
            "label": label,
            "items": list(items),
            "worker": worker,
            "done": done,
            "item_label": item_label,
        }


def test_selected_scope_single_line_routes_to_shared_parallel_batch_runner() -> None:
    source = (ROOT / "src/picture_capture/ui/controllers/crop.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    crop_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CropController"
    )
    method = next(
        node for node in crop_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "split_single_lines_selected_scope"
    )
    method_text = ast.get_source_segment(source, method) or ""

    assert "_snapshot_scope(app)" in method_text
    assert "app._start_parallel_batch_task(" in method_text
    assert "single_line_page_job" in method_text
    assert "start_single_line_export" not in method_text


def test_batch_active_short_circuits_before_guards() -> None:
    app = _App()
    app._batch_active = True

    CropController(app).split_lines_current()

    assert app.calls == []
    assert app.batch is None
    assert app.status_var.values == ["已有批量任务正在运行，请结束后再执行单行切图。"]


def test_guard_and_geometry_short_circuit_in_original_order() -> None:
    app = _App()
    app.guard_result = False

    CropController(app).split_lines_current()

    assert app.calls == [("guard",)]
    assert app.batch is None

    app = _App()
    app.geometry_result = False

    CropController(app).split_lines_current()

    assert app.calls == [("guard",), ("guard_geometry", "单行切图")]
    assert app.batch is None


def test_single_line_action_snapshots_current_page_and_starts_original_batch(monkeypatch) -> None:
    app = _App()
    monkeypatch.setattr(crop_module, "qt_root", lambda root: Path("/normalized/QT"))

    CropController(app).split_lines_current()

    assert app.calls == [
        ("guard",),
        ("guard_geometry", "单行切图"),
        ("start_batch", "当前页单行切图", [2]),
    ]
    assert app.batch is not None
    assert app.batch["label"] == "当前页单行切图"
    assert app.batch["items"] == [2]
    assert app.batch["item_label"](object()) == "page001.png"


def test_worker_uses_snapshots_logs_records_and_returns_record_count(monkeypatch) -> None:
    app = _App()
    captured: dict[str, object] = {}
    records = [object(), object(), object()]
    monkeypatch.setattr(crop_module, "qt_root", lambda root: Path("/normalized/QT"))

    def fake_split(page, entries, settings, out_dir, *, profile_page_index):
        captured["page"] = page
        captured["entries"] = entries
        captured["settings"] = settings
        captured["out_dir"] = out_dir
        captured["page_index"] = profile_page_index
        return records

    logged: list[tuple[Path, list[object]]] = []
    monkeypatch.setattr(crop_module, "split_single_lines", fake_split)
    monkeypatch.setattr(
        crop_module,
        "append_crop_log",
        lambda root, rows: logged.append((root, list(rows))),
    )

    CropController(app).split_lines_current()
    assert app.batch is not None

    app.entries[0].word = "mutated"
    app.settings.marker = 99
    result = app.batch["worker"](2, 1, 1)

    assert result == 3
    assert captured == {
        "page": Path("/pages/page001.png"),
        "entries": [_Entry("one"), _Entry("two")],
        "settings": _Settings(marker=7),
        "out_dir": Path("/normalized/QT/PSW"),
        "page_index": 2,
    }
    assert captured["entries"] is not app.entries
    assert captured["settings"] is not app.settings
    assert logged == [(Path("/project"), records)]


def test_done_preserves_success_only_status_semantics() -> None:
    app = _App()
    CropController(app).split_lines_current()
    assert app.batch is not None
    done = app.batch["done"]

    done(1, 1, False, [5], None)
    assert app.status_var.values == ["已导出 5 张词条单行图"]

    app.status_var.values.clear()
    done(1, 1, True, [5], None)
    done(1, 1, False, [], None)
    done(1, 1, False, [5], RuntimeError("failed"))
    assert app.status_var.values == []


def test_whole_entry_batch_active_short_circuits_before_guards() -> None:
    app = _App()
    app._batch_active = True

    CropController(app).split_whole_current()

    assert app.calls == []
    assert app.batch is None
    assert app.status_var.values == ["已有批量任务正在运行，请结束后再执行整体切图。"]


def test_whole_entry_guard_and_geometry_short_circuit_before_settings_lookup() -> None:
    app = _App()
    app.guard_result = False

    CropController(app).split_whole_current()

    assert app.calls == [("guard",)]
    assert app.batch is None

    app = _App()
    app.geometry_result = False

    CropController(app).split_whole_current()

    assert app.calls == [("guard",), ("guard_geometry", "整体切图")]
    assert app.batch is None


def test_whole_entry_action_loads_crop_settings_and_starts_original_batch(monkeypatch) -> None:
    app = _App()
    monkeypatch.setattr(crop_module, "qt_root", lambda root: Path("/normalized/QT"))

    CropController(app).split_whole_current()

    assert app.calls == [
        ("guard",),
        ("guard_geometry", "整体切图"),
        ("load_crop_settings",),
        ("start_batch", "当前页整体切图", [2]),
    ]
    assert app.batch is not None
    assert app.batch["label"] == "当前页整体切图"
    assert app.batch["items"] == [2]
    assert app.batch["item_label"](object()) == "page001.png"


def test_whole_entry_worker_uses_snapshots_settings_and_logs_records(monkeypatch) -> None:
    app = _App()
    captured: dict[str, object] = {}
    records = [object(), object()]
    monkeypatch.setattr(crop_module, "qt_root", lambda root: Path("/normalized/QT"))

    def fake_split(
        page, entries, settings, out_dir, *, top_y, bottom_y, polygons,
        entry_left_padding, entry_right_padding, integrate_illustrations,
        profile_page_index,
    ):
        captured.update(
            page=page,
            entries=entries,
            settings=settings,
            out_dir=out_dir,
            top_y=top_y,
            bottom_y=bottom_y,
            polygons=polygons,
            entry_left_padding=entry_left_padding,
            entry_right_padding=entry_right_padding,
            integrate_illustrations=integrate_illustrations,
            page_index=profile_page_index,
        )
        return records

    logged: list[tuple[Path, list[object]]] = []
    monkeypatch.setattr(crop_module, "split_whole_entries", fake_split)
    monkeypatch.setattr(
        crop_module,
        "append_crop_log",
        lambda root, rows: logged.append((root, list(rows))),
    )

    CropController(app).split_whole_current()
    assert app.batch is not None

    original_polygons = list(app.polygons)
    app.entries[0].word = "mutated"
    app.settings.marker = 99
    app.polygons.append("poly-c")
    app.crop_config["special_pages"]["page001"]["top_y"] = 999
    result = app.batch["worker"](2, 1, 1)

    assert result == 2
    assert captured == {
        "page": Path("/pages/page001.png"),
        "entries": [_Entry("one"), _Entry("two")],
        "settings": _Settings(marker=7),
        "out_dir": Path("/normalized/QT/PWW"),
        "top_y": 23,
        "bottom_y": 456,
        "polygons": original_polygons,
        "entry_left_padding": 4,
        "entry_right_padding": 7,
        "integrate_illustrations": False,
        "page_index": 2,
    }
    assert captured["entries"] is not app.entries
    assert captured["settings"] is not app.settings
    assert captured["polygons"] is not app.polygons
    assert logged == [(Path("/project"), records)]


def test_whole_entry_done_preserves_success_only_status_semantics() -> None:
    app = _App()
    CropController(app).split_whole_current()
    assert app.batch is not None
    done = app.batch["done"]

    done(1, 1, False, [4], None)
    assert app.status_var.values == ["已导出 4 张词条整体图"]

    app.status_var.values.clear()
    done(1, 1, True, [4], None)
    done(1, 1, False, [], None)
    done(1, 1, False, [4], RuntimeError("failed"))
    assert app.status_var.values == []


def test_batch_whole_silent_noop_without_project_or_while_batch_active() -> None:
    app = _App()
    app.project = None

    CropController(app).batch_split_whole()

    assert app.calls == []
    assert app.batch is None
    assert app.status_var.values == []

    app = _App()
    app._batch_active = True

    CropController(app).batch_split_whole()

    assert app.calls == []
    assert app.batch is None
    assert app.status_var.values == []


def test_batch_whole_geometry_guard_short_circuits_before_settings_lookup() -> None:
    app = _App()
    app.geometry_result = False

    CropController(app).batch_split_whole()

    assert app.calls == [("guard_geometry", "批量整体切图")]
    assert app.batch is None


def test_batch_whole_selects_all_pages_and_preserves_batch_label(monkeypatch) -> None:
    app = _App()
    monkeypatch.setattr(crop_module, "qt_root", lambda root: Path("/normalized/QT"))

    CropController(app).batch_split_whole()

    assert app.calls == [
        ("guard_geometry", "批量整体切图"),
        ("load_crop_settings",),
        ("start_batch", "批量整体切图", [0, 1]),
    ]
    assert app.batch is not None
    assert app.batch["label"] == "批量整体切图"
    assert app.batch["items"] == [0, 1]
    assert app.batch["item_label"](0) == "page001.png"
    assert app.batch["item_label"](1) == "page002.png"


def test_batch_whole_worker_reads_pdic_ppp_uses_overrides_and_settings_snapshot(monkeypatch) -> None:
    app = _App()
    calls: list[tuple] = []
    captured: dict[str, object] = {}
    records = [object(), object(), object()]
    entries = [_Entry("disk-one"), _Entry("disk-two")]
    polygons = ["disk-poly"]

    monkeypatch.setattr(crop_module, "qt_root", lambda root: Path("/normalized/QT"))

    def fake_pdic_path(page: Path) -> Path:
        path = Path("/pdic") / f"{page.stem}.pdic"
        calls.append(("pdic_path", page, path))
        return path

    def fake_ppp_path(page: Path) -> Path:
        path = Path("/ppp") / f"{page.stem}.ppp"
        calls.append(("ppp_path", page, path))
        return path

    def fake_read_pdic(path: Path):
        calls.append(("read_pdic", path))
        return entries

    def fake_read_ppp(path: Path):
        calls.append(("read_ppp", path))
        return polygons

    def fake_split(
        page, worker_entries, settings, out_dir, *, top_y, bottom_y, polygons,
        entry_left_padding, entry_right_padding, integrate_illustrations,
        profile_page_index,
    ):
        captured.update(
            page=page,
            entries=worker_entries,
            settings=settings,
            out_dir=out_dir,
            top_y=top_y,
            bottom_y=bottom_y,
            polygons=polygons,
            entry_left_padding=entry_left_padding,
            entry_right_padding=entry_right_padding,
            integrate_illustrations=integrate_illustrations,
            page_index=profile_page_index,
        )
        return records

    logged: list[tuple[Path, list[object]]] = []
    monkeypatch.setattr(crop_module, "pdic_path", fake_pdic_path)
    monkeypatch.setattr(crop_module, "ppp_read_path_for_image", fake_ppp_path)
    monkeypatch.setattr(crop_module, "read_pdic", fake_read_pdic)
    monkeypatch.setattr(crop_module, "read_ppp", fake_read_ppp)
    monkeypatch.setattr(crop_module, "split_whole_entries", fake_split)
    monkeypatch.setattr(
        crop_module,
        "append_crop_log",
        lambda root, rows: logged.append((root, list(rows))),
    )

    CropController(app).batch_split_whole()
    assert app.batch is not None

    app.settings.marker = 99
    result = app.batch["worker"](0, 1, 2)

    assert result == 3
    assert calls == [
        ("pdic_path", Path("/pages/page001.png"), Path("/pdic/page001.pdic")),
        ("read_pdic", Path("/pdic/page001.pdic")),
        ("ppp_path", Path("/pages/page001.png"), Path("/ppp/page001.ppp")),
        ("read_ppp", Path("/ppp/page001.ppp")),
    ]
    assert captured == {
        "page": Path("/pages/page001.png"),
        "entries": entries,
        "settings": _Settings(marker=7),
        "out_dir": Path("/normalized/QT/PWW"),
        "top_y": 23,
        "bottom_y": 456,
        "polygons": polygons,
        "entry_left_padding": 4,
        "entry_right_padding": 7,
        "integrate_illustrations": False,
        "page_index": 0,
    }
    assert captured["settings"] is not app.settings
    assert logged == [(Path("/project"), records)]


def test_batch_whole_worker_uses_general_bounds_when_page_has_no_override(monkeypatch) -> None:
    app = _App()
    captured: dict[str, int] = {}
    monkeypatch.setattr(crop_module, "qt_root", lambda root: Path("/normalized/QT"))
    monkeypatch.setattr(crop_module, "pdic_path", lambda page: Path("/pdic") / f"{page.stem}.pdic")
    monkeypatch.setattr(crop_module, "ppp_read_path_for_image", lambda page: Path("/ppp") / f"{page.stem}.ppp")
    monkeypatch.setattr(crop_module, "read_pdic", lambda _path: [])
    monkeypatch.setattr(crop_module, "read_ppp", lambda _path: [])

    def fake_split(_page, _entries, _settings, _out_dir, **kwargs):
        captured["top_y"] = kwargs["top_y"]
        captured["bottom_y"] = kwargs["bottom_y"]
        return []

    monkeypatch.setattr(crop_module, "split_whole_entries", fake_split)
    monkeypatch.setattr(crop_module, "append_crop_log", lambda _root, _rows: None)

    CropController(app).batch_split_whole()
    assert app.batch is not None
    app.batch["worker"](1, 2, 2)

    assert captured == {"top_y": 13, "bottom_y": 777}


def test_batch_whole_done_preserves_error_stopped_and_completed_statuses() -> None:
    app = _App()
    CropController(app).batch_split_whole()
    assert app.batch is not None
    done = app.batch["done"]

    done(1, 2, False, [2, 3], RuntimeError("failed"))
    assert app.status_var.values == []

    done(1, 2, True, [2, None, 3], None)
    assert app.status_var.values == ["批量整体切图已停止：完成 1/2 页，共 5 张"]

    app.status_var.values.clear()
    done(2, 2, False, [2, None, 3], None)
    assert app.status_var.values == ["批量整体切图完成：5 张"]


def test_crop_controller_has_no_reverse_dependency_on_app_module() -> None:
    path = ROOT / "src/picture_capture/ui/controllers/crop.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_crop_controller_wiring_preserves_app_compatibility_methods() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controllers = (
        ROOT / "src/picture_capture/ui/controllers/__init__.py"
    ).read_text(encoding="utf-8")
    controller = (
        ROOT / "src/picture_capture/ui/controllers/crop.py"
    ).read_text(encoding="utf-8")

    imports = app[: app.index("class PictureCaptureApp")]
    assert "CropController" in imports
    assert "self.crop_controller = CropController(self)" in app
    assert app.index("self.crop_controller = CropController(self)") < app.index("self._build_ui()")
    assert "def _crop_controller_for_call(" in app
    assert 'self.__dict__.get("crop_controller")' in app
    assert "def split_lines_current(self)" in app
    assert "self._crop_controller_for_call().split_lines_current()" in app
    assert "def split_whole_current(self)" in app
    assert "self._crop_controller_for_call().split_whole_current()" in app
    assert "def batch_split_whole(self)" in app
    assert "self._crop_controller_for_call().batch_split_whole()" in app
    assert "from .crop import CropController" in controllers
    assert '"CropController"' in controllers
    assert "class CropController" in controller


def test_phase4k_leaves_other_crop_and_runtime_paths_untouched() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    runtime_path = ROOT / "src/picture_capture/postproduction_single_line_runtime.py"
    controller = (
        ROOT / "src/picture_capture/ui/controllers/crop.py"
    ).read_text(encoding="utf-8")

    assert "def _crop_settings_defaults(self)" in app
    assert "def detect_illustrations_selected_scope(self)" in app
    assert not runtime_path.exists()
    assert "def split_single_lines_selected_scope(self)" in app
    assert "self._crop_controller_for_call().split_single_lines_selected_scope()" in app
    tree = ast.parse(controller)
    crop_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CropController"
    )
    method_names = {
        node.name for node in crop_class.body if isinstance(node, ast.FunctionDef)
    }
    assert "split_lines_current" in method_names
    assert "split_whole_current" in method_names
    assert "batch_split_whole" in method_names
    assert "_crop_settings_defaults" not in method_names
    assert "detect_illustrations_selected_scope" not in method_names
    assert "split_single_lines_selected_scope" in method_names
