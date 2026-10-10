from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui.controllers.page import PageController


ROOT = Path(__file__).resolve().parents[1]


class _Status:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class _PageList:
    def __init__(self, selection=("2",), focus="2") -> None:
        self._selection = selection
        self._focus = focus

    def selection(self):
        return self._selection

    def focus(self):
        return self._focus


def test_page_controller_has_no_reverse_app_dependency() -> None:
    import picture_capture.ui.controllers.page as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_page_selection_routes_through_controller_request() -> None:
    app = SimpleNamespace(
        _batch_active=False,
        _batch_foreground_pages=False,
        _batch_allow_page_navigation=False,
        current_index=1,
        _pending_page_index=None,
        page_list=_PageList(),
        status_var=_Status(),
    )
    controller = PageController(app)
    requested: list[int] = []
    controller.request_page_load = lambda index, **_kwargs: requested.append(index) or True

    controller.on_page_select(None)

    assert requested == [2]


def test_page_selection_batch_guard_keeps_current_page_selected() -> None:
    selected: list[tuple[int, bool]] = []
    app = SimpleNamespace(
        _batch_active=True,
        _batch_foreground_pages=False,
        _batch_allow_page_navigation=False,
        current_index=3,
        _pending_page_index=None,
        page_list=_PageList(),
        status_var=_Status(),
        _set_page_list_selection=lambda index, ensure_visible=False: selected.append(
            (index, ensure_visible)
        ),
    )
    controller = PageController(app)

    controller.on_page_select(None)

    assert selected == [(3, False)]
    assert "暂不允许切换页面" in app.status_var.value


def test_rejected_selection_followup_event_does_not_restore_again() -> None:
    page_list = _PageList(selection=("8",), focus="8")
    restored = []
    app = SimpleNamespace(
        _batch_active=True,
        _batch_foreground_pages=False,
        _batch_allow_page_navigation=False,
        current_index=3,
        _pending_page_index=None,
        page_list=page_list,
        status_var=_Status(),
    )

    def restore(index: int, *, ensure_visible: bool = True) -> None:
        restored.append((index, ensure_visible))
        page_list._selection = (str(index),)

    app._set_page_list_selection = restore
    controller = PageController(app)
    controller.on_page_select(None)
    controller.on_page_select(None)  # Tk emits another event for restoration.
    assert restored == [(3, False)]


def test_selection_restore_avoids_empty_selection_and_duplicate_events() -> None:
    source = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = source.index("    def _set_page_list_selection(")
    end = source.index("    def _select_page_from_lined_overlay(", start)
    block = source[start:end]
    assert "stale = tuple(value for value in selected if value != iid)" in block
    assert "self.page_list.selection_remove(*stale)" in block
    assert "if iid not in selected:" in block
    assert "self.page_list.selection_set(iid)" in block


def test_change_page_uses_controller_async_request_before_core_load() -> None:
    app = SimpleNamespace(
        _batch_active=False,
        _batch_foreground_pages=False,
        _batch_allow_page_navigation=False,
        project=SimpleNamespace(images=[object(), object(), object()]),
        current_index=1,
        _pending_page_index=None,
        status_var=_Status(),
    )
    controller = PageController(app)
    requested: list[tuple[int, bool]] = []
    controller.request_page_load = lambda index, **kwargs: requested.append(
        (index, bool(kwargs.get("current_already_saved", False)))
    ) or True

    assert controller.change_page(1, current_already_saved=True) is True
    assert requested == [(2, True)]


def test_page_controller_wiring_keeps_picture_capture_app_compatibility_methods() -> None:
    app = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    controller = (
        ROOT / "src" / "picture_capture" / "ui" / "controllers" / "page.py"
    ).read_text(encoding="utf-8")

    imports = app[:app.index("class PictureCaptureApp")]
    assert "PageController" in imports
    assert "self.page_controller = PageController(self)" in app
    assert app.index("self.page_controller = PageController(self)") < app.index("self._build_ui()")

    app_start = app.index("class PictureCaptureApp")
    select_start = app.index("    def on_page_select(", app_start)
    request_start = app.index("    def _request_page_load(", select_start)
    load_start = app.index("    def load_page(", request_start)
    change_start = app.index("    def change_page(", load_start)
    after_change = app.index("\n    def ", change_start + 10)

    assert "self.page_controller.on_page_select" in app[select_start:request_start]
    assert "self.page_controller.request_page_load" in app[request_start:load_start]
    assert "self.page_controller.change_page" in app[change_start:after_change]

    # Page-state commit remains intentionally owned by PictureCaptureApp in 4A.
    load_block = app[load_start:change_start]
    assert "self.current_index = index" in load_block
    assert "self.redraw()" in load_block

    # Background decoding/preload ownership has moved to the controller.
    assert "with Image.open(page) as opened:" in controller
    assert 'app._start_ui_worker("page-load"' in controller
