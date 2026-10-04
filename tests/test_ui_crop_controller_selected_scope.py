from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import picture_capture.ui.controllers.crop as crop_module
from picture_capture.ui.controllers.crop import CropController


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class _Settings:
    start_y: int = 11
    crop_parallel_workers: int = 3
    marker: int = 7


class _StatusVar:
    def __init__(self) -> None:
        self.values: list[str] = []

    def set(self, value: str) -> None:
        self.values.append(value)


class _App:
    def __init__(self) -> None:
        self.project = SimpleNamespace(
            root=Path("/project"),
            images=[Path("/pages/page001.png"), Path("/pages/page002.png")],
        )
        self.settings = _Settings()
        self.crop_config = {
            "general_top_y": 13,
            "general_bottom_y": 777,
            "entry_left_padding_x": 4,
            "entry_right_padding_x": 7,
            "integrate_illustrations": False,
            "parallel_workers": 5,
            "special_pages": {
                "page002": {"top_y": 23, "bottom_y": 456},
            },
        }
        self.status_var = _StatusVar()
        self.guard_result = True
        self.geometry_result = True
        self.indices: list[int] = [1]
        self.range_error: Exception | None = None
        self.calls: list[tuple] = []
        self.errors: list[tuple[str, Exception]] = []
        self.parallel: dict[str, object] | None = None

    def guard(self) -> bool:
        self.calls.append(("guard",))
        return self.guard_result

    def selected_page_indices(self) -> list[int]:
        self.calls.append(("selected_page_indices",))
        if self.range_error is not None:
            raise self.range_error
        return list(self.indices)

    def show_error(self, title: str, exc: Exception) -> None:
        self.calls.append(("show_error", title, exc))
        self.errors.append((title, exc))

    def _guard_transformed_geometry(self, action: str) -> bool:
        self.calls.append(("guard_geometry", action))
        return self.geometry_result

    def save_pdic(self, silent: bool = False) -> None:
        self.calls.append(("save_pdic", silent))

    def _load_crop_settings(self) -> dict:
        self.calls.append(("load_crop_settings",))
        return self.crop_config

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
        self.calls.append(("start_parallel", title, list(items), max_workers))
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


def test_selected_scope_guard_false_is_noop() -> None:
    app = _App()
    app.guard_result = False

    CropController(app).split_entries_selected_scope()

    assert app.calls == [("guard",)]
    assert app.parallel is None
    assert app.errors == []


def test_invalid_page_range_preserves_error_before_new_geometry_gate() -> None:
    app = _App()
    problem = ValueError("bad range")
    app.range_error = problem

    CropController(app).split_entries_selected_scope()

    assert app.calls == [
        ("guard",),
        ("selected_page_indices",),
        ("show_error", "页面范围无效", problem),
    ]
    assert app.errors == [("页面范围无效", problem)]
    assert app.parallel is None


def test_new_geometry_guard_blocks_before_save_or_settings_lookup() -> None:
    app = _App()
    app.geometry_result = False

    CropController(app).split_entries_selected_scope()

    assert app.calls == [
        ("guard",),
        ("selected_page_indices",),
        ("guard_geometry", "词条切图"),
    ]
    assert app.parallel is None


def test_selected_scope_saves_then_starts_parallel_job_with_original_contract(monkeypatch) -> None:
    app = _App()
    monkeypatch.setattr(crop_module, "qt_root", lambda _root: Path("/normalized/QT"))

    CropController(app).split_entries_selected_scope()

    assert app.calls == [
        ("guard",),
        ("selected_page_indices",),
        ("guard_geometry", "词条切图"),
        ("save_pdic", True),
        ("load_crop_settings",),
        ("start_parallel", "词条切图", [1], 5),
    ]
    assert app.parallel is not None
    assert app.parallel["title"] == "词条切图"
    assert app.parallel["items"] == [1]
    assert app.parallel["worker_func"] is crop_module.split_whole_entries_job
    assert app.parallel["max_workers"] == 5
    assert app.parallel["item_label"](1) == "page002.png"


def test_job_builder_uses_storage_ppp_helper_overrides_and_settings_snapshot(monkeypatch) -> None:
    app = _App()
    calls: list[tuple] = []
    monkeypatch.setattr(crop_module, "qt_root", lambda _root: Path("/normalized/QT"))

    def fake_pdic_path(page: Path) -> Path:
        path = Path("/pdic") / f"{page.stem}.pdic"
        calls.append(("pdic", page, path))
        return path

    def fake_ppp_path(page: Path) -> Path:
        path = Path("/ppp") / f"{page.stem}.ppp"
        calls.append(("ppp", page, path))
        return path

    monkeypatch.setattr(crop_module, "pdic_path", fake_pdic_path)
    monkeypatch.setattr(crop_module, "ppp_read_path_for_image", fake_ppp_path)

    CropController(app).split_entries_selected_scope()
    assert app.parallel is not None

    app.settings.marker = 99
    payload = app.parallel["job_builder"](1, 1, 1)

    assert calls == [
        ("pdic", Path("/pages/page002.png"), Path("/pdic/page002.pdic")),
        ("ppp", Path("/pages/page002.png"), Path("/ppp/page002.ppp")),
    ]
    assert payload == (
        str(Path("/pages/page002.png")),
        str(Path("/pdic/page002.pdic")),
        _Settings(start_y=11, crop_parallel_workers=3, marker=7),
        str(Path("/normalized/QT") / "PWW"),
        23,
        456,
        str(Path("/ppp/page002.ppp")),
        4,
        7,
        False,
        1,
    )
    assert payload[2] is not app.settings


def test_result_consumer_logs_records_and_done_preserves_status_contract(monkeypatch) -> None:
    app = _App()
    logged: list[tuple[Path, list[object]]] = []
    monkeypatch.setattr(
        crop_module,
        "append_crop_log",
        lambda root, records: logged.append((root, list(records))),
    )

    CropController(app).split_entries_selected_scope()
    assert app.parallel is not None
    consume = app.parallel["result_consumer"]
    done = app.parallel["on_done"]

    records = [object(), object(), object()]
    assert consume(1, records) == 3
    assert logged == [(Path("/project"), records)]

    done(1, 1, False, [3], None)
    assert app.status_var.values == ["词条切图完成：1 页，共 3 张"]

    app.status_var.values.clear()
    done(1, 2, True, [3], None)
    assert app.status_var.values == ["词条切图已停止：完成 1/2 页，共导出 3 张"]

    app.status_var.values.clear()
    done(1, 1, False, [3], RuntimeError("failed"))
    assert app.status_var.values == []


def test_phase4l_direct_ppp_storage_boundary_and_app_compatibility_wrapper() -> None:
    app_text = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller_text = (
        ROOT / "src/picture_capture/ui/controllers/crop.py"
    ).read_text(encoding="utf-8")

    tree = ast.parse(controller_text)
    crop_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CropController"
    )
    method = next(
        node for node in crop_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "split_entries_selected_scope"
    )
    method_text = ast.get_source_segment(controller_text, method) or ""

    assert "ppp_read_path_for_image(page)" in method_text
    assert "_ppp_read_path" not in method_text
    assert '_guard_transformed_geometry("词条切图")' in method_text
    assert "def split_entries_selected_scope(self)" in app_text
    assert "self._crop_controller_for_call().split_entries_selected_scope()" in app_text


def test_phase4l_leaves_parallel_runner_illustration_and_runtime_paths_in_app() -> None:
    app_text = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller_text = (
        ROOT / "src/picture_capture/ui/controllers/crop.py"
    ).read_text(encoding="utf-8")
    runtime_text = (
        ROOT / "src/picture_capture/postproduction_single_line_runtime.py"
    ).read_text(encoding="utf-8")

    assert "def _start_parallel_batch_task(" in app_text
    assert "def detect_illustrations_selected_scope(self)" in app_text
    assert "def split_illustrations_selected_scope(self)" in app_text
    assert "detect_illustrations_selected_scope" not in controller_text
    assert "split_illustrations_selected_scope" not in controller_text
    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" in runtime_text


def test_postproduction_button_still_targets_app_compatibility_method() -> None:
    app_text = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    assert '("词条切图", self.split_entries_selected_scope)' in app_text
