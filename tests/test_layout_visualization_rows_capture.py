from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import picture_capture.layout_visualization_shared as shared


def test_shared_snapshot_seeds_layoutrows_with_persisted_app_settings(monkeypatch, tmp_path):
    page = tmp_path / "000003.png"
    page.write_bytes(b"page")
    settings = object()
    app = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path, images=[page]),
        current_index=0,
        settings=settings,
    )
    events: list[object] = []

    @contextmanager
    def fake_capture(project_root, image_path, page_index, captured_settings):
        events.append((Path(project_root), Path(image_path), page_index, captured_settings))
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")

    monkeypatch.setattr(shared, "capture_layout_rows", fake_capture)
    monkeypatch.setattr(
        shared, "_shared_snapshot_for_app_impl", lambda value: events.append(("impl", value)) or "snapshot"
    )

    assert shared.shared_snapshot_for_app(app) == "snapshot"
    assert events == [
        (tmp_path, page, 0, settings),
        "enter",
        ("impl", app),
        "exit",
    ]


def test_shared_snapshot_capture_fallbacks_preserve_historical_control_flow(monkeypatch, tmp_path):
    calls: list[object] = []

    @contextmanager
    def forbidden_capture(*args, **kwargs):
        raise AssertionError("capture must not start for invalid visualization context")
        yield

    monkeypatch.setattr(shared, "capture_layout_rows", forbidden_capture)
    monkeypatch.setattr(
        shared, "_shared_snapshot_for_app_impl", lambda app: calls.append(app) or "fallback"
    )

    no_project = SimpleNamespace(project=None)
    assert shared.shared_snapshot_for_app(no_project) == "fallback"

    invalid_index = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path, images=[]), current_index=8, settings=object()
    )
    assert shared.shared_snapshot_for_app(invalid_index) == "fallback"

    no_settings = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path, images=[tmp_path / "x.png"]),
        current_index=0,
        settings=None,
    )
    assert shared.shared_snapshot_for_app(no_settings) == "fallback"
    assert calls == [no_project, invalid_index, no_settings]


def test_phase5h_source_shape_keeps_later_visualization_decorators_and_removes_runtime():
    root = Path(__file__).resolve().parents[1]
    package = root / "src" / "picture_capture"
    gui = (package / "bootstrap" / "gui.py").read_text(encoding="utf-8")
    guard = (root / "scripts" / "architecture_guard.py").read_text(encoding="utf-8")

    assert not (package / "layout_visualization_rows_cache_runtime.py").exists()
    assert "install_layout_visualization_rows_cache" not in gui
    assert "layout_visualization_rows_cache_runtime.py" not in guard
    assert "install_local_indent_visualization" not in gui
    assert "install_layout_role_provenance" not in gui
    shared_pos = gui.index("install_shared_layout_visualization_source()")
    role_theme_pos = gui.index("install_layout_role_theme()")
    assert shared_pos < role_theme_pos
