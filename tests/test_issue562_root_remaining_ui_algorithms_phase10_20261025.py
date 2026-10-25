"""Issue #562: real owners for main UI navigation, worker and environment algorithms."""
from __future__ import annotations
import inspect
from types import SimpleNamespace
from picture_capture import app
from picture_capture.ui import (
    main_sidebar_sections, page_index_workflow, main_app_lifecycle,
    background_job_runtime, paddle_environment_report,
)


def test_real_owners_and_stable_root_public_methods():
    owners = {
        main_sidebar_sections: ("_pointer_over_sidebar", "_sidebar_mousewheel", "_sidebar_linux_mousewheel"),
        page_index_workflow: ("_list_mousewheel", "_select_page_from_lined_overlay"),
        main_app_lifecycle: ("_guard_transformed_geometry",),
        background_job_runtime: ("_ui_worker_key_active", "_invalidate_ui_worker"),
        paddle_environment_report: ("_distribution_version", "_version_at_least"),
    }
    for owner, names in owners.items():
        for name in names:
            public = getattr(app.PictureCaptureApp, name)
            implementation = getattr(owner, name)
            assert public.__module__ == "picture_capture.app"
            assert "return _" in inspect.getsource(public)
            assert len(inspect.getsource(implementation).splitlines()) >= 3
    assert "winfo_pointerx()" in inspect.getsource(main_sidebar_sections._pointer_over_sidebar)
    assert "self._request_page_load(index)" in inspect.getsource(page_index_workflow._select_page_from_lined_overlay)


def test_sidebar_pointer_hit_testing_and_wheel():
    scrolls = []
    canvas = SimpleNamespace(
        winfo_pointerx=lambda: 120, winfo_pointery=lambda: 140,
        winfo_rootx=lambda: 100, winfo_rooty=lambda: 100,
        winfo_width=lambda: 150, winfo_height=lambda: 80,
        yview_scroll=lambda n, unit: scrolls.append((n, unit)),
    )
    obj = SimpleNamespace(sidebar_canvas=canvas)
    assert app.PictureCaptureApp._pointer_over_sidebar(obj) is True
    obj._pointer_over_sidebar = lambda: app.PictureCaptureApp._pointer_over_sidebar(obj)
    assert app.PictureCaptureApp._sidebar_mousewheel(obj, SimpleNamespace(delta=120)) == "break"
    assert app.PictureCaptureApp._sidebar_linux_mousewheel(obj, None, 1) == "break"
    assert scrolls == [(-3, "units"), (3, "units")]
    canvas.winfo_pointerx = lambda: 10
    assert app.PictureCaptureApp._pointer_over_sidebar(obj) is False
    assert app.PictureCaptureApp._sidebar_mousewheel(obj, SimpleNamespace(delta=120)) is None


def test_page_overlay_navigates_without_synthetic_treeview_event():
    loaded, selected = [], []
    obj = SimpleNamespace(
        project=SimpleNamespace(images=[1, 2, 3]), current_index=1,
        _request_page_load=lambda i: loaded.append(i),
        _set_page_list_selection=lambda i, ensure_visible: selected.append((i, ensure_visible)),
    )
    app.PictureCaptureApp._select_page_from_lined_overlay(obj, 2)
    app.PictureCaptureApp._select_page_from_lined_overlay(obj, 1)
    app.PictureCaptureApp._select_page_from_lined_overlay(obj, 7)
    assert loaded == [2]
    assert selected == [(1, True)]


def test_ui_worker_generation_invalidation_keeps_unrelated_keys():
    obj = SimpleNamespace(
        _ui_worker_active={("scan", 1), ("ocr", 3)},
        _ui_worker_generations={"scan": 1, "ocr": 3},
        _ui_worker_handlers={("scan", 1): "old", ("ocr", 3): "keep"},
    )
    assert app.PictureCaptureApp._ui_worker_key_active(obj, "scan")
    assert not app.PictureCaptureApp._ui_worker_key_active(obj, "missing")
    app.PictureCaptureApp._invalidate_ui_worker(obj, "scan")
    assert obj._ui_worker_generations == {"scan": 2, "ocr": 3}
    assert obj._ui_worker_handlers == {("ocr", 3): "keep"}


def test_transformed_geometry_write_guard_and_paddle_versions():
    statuses = []
    obj = SimpleNamespace(settings=SimpleNamespace(layout_transform="unknown"),
                          status_var=SimpleNamespace(set=statuses.append))
    assert app.PictureCaptureApp._guard_transformed_geometry(obj, "裁剪") is False
    assert "PDIC" in statuses[-1]
    obj.settings.layout_transform = "identity"
    assert app.PictureCaptureApp._guard_transformed_geometry(obj, "裁剪") is True
    assert app.PictureCaptureApp._version_at_least("3.7.0rc1", (3, 7)) is True
    assert app.PictureCaptureApp._version_at_least(None, (3, 7)) is False
    assert app.PictureCaptureApp._version_at_least("unknown", (3, 7)) is False
