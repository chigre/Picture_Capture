from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


# layout_visualization_shared.py: make the currently installed capture wrapper
# the static public entry while preserving the existing snapshot body verbatim.
path = "src/picture_capture/layout_visualization_shared.py"
text = read(path)
text = replace_once(
    text,
    "from typing import Any\n\nfrom .dictionary_page_layout_policy import resolve_page_layout_policy\n",
    "from pathlib import Path\nfrom typing import Any\n\nfrom .dictionary_page_layout_policy import resolve_page_layout_policy\n"
    "from .layout_rows_cache import capture_layout_rows\n",
    label="shared imports",
)
text = replace_once(
    text,
    "def shared_snapshot_for_app(app: Any) -> Any:\n"
    "    \"\"\"Return a LayoutVisualizationSnapshot from the ordinary shared geometry.\"\"\"\n",
    "def _shared_snapshot_for_app_impl(app: Any) -> Any:\n"
    "    \"\"\"Build the ordinary shared Layout snapshot without cache-capture routing.\"\"\"\n",
    label="shared impl rename",
)
marker = "\n\ndef install_shared_layout_visualization_source() -> None:\n"
wrapper = '''\n\ndef shared_snapshot_for_app(app: Any) -> Any:\n    \"\"\"Return the shared Layout snapshot while seeding the physical-row cache.\"\"\"\n    project = getattr(app, \"project\", None)\n    if project is None:\n        return _shared_snapshot_for_app_impl(app)\n    try:\n        index = max(0, int(getattr(app, \"current_index\", 0)))\n        images = list(getattr(project, \"images\", []) or [])\n    except Exception:\n        return _shared_snapshot_for_app_impl(app)\n    if not (0 <= index < len(images)):\n        return _shared_snapshot_for_app_impl(app)\n\n    # Preserve the historical visualization-runtime contract: cache identity is\n    # based on persisted app settings, while the snapshot implementation remains\n    # free to derive page-effective settings internally.\n    settings = getattr(app, \"settings\", None)\n    if settings is None:\n        return _shared_snapshot_for_app_impl(app)\n    with capture_layout_rows(\n        Path(project.root),\n        Path(images[index]),\n        index,\n        settings,\n    ):\n        return _shared_snapshot_for_app_impl(app)\n'''
text = replace_once(text, marker, wrapper + marker, label="shared wrapper insertion")
write(path, text)


# GUI composition: shared snapshot now owns capture statically; remove only the
# dedicated rows-cache visualization installer. Keep later visualization order.
path = "src/picture_capture/bootstrap/gui.py"
text = read(path)
text = replace_once(
    text,
    "    from ..layout_visualization_rows_cache_runtime import (\n"
    "        install_layout_visualization_rows_cache,\n"
    "    )\n",
    "",
    label="gui rows-cache import",
)
text = replace_once(
    text,
    "    # Wrap the shared Layout snapshot before it is published to the UI. When a\n"
    "    # user displays Layout, the exact physical rows are persisted for later QA;\n"
    "    # the cache identity uses project settings, matching post-production export.\n"
    "    install_layout_visualization_rows_cache()\n"
    "    install_shared_layout_visualization_source()\n",
    "    # The shared Layout snapshot now owns its LayoutRows capture context\n"
    "    # statically before being published to the UI.\n"
    "    install_shared_layout_visualization_source()\n",
    label="gui rows-cache call",
)
write(path, text)


# Ratchet the retired runtime filename out of the architecture-debt baseline.
path = "scripts/architecture_guard.py"
text = read(path)
text = replace_once(
    text,
    '    "layout_visualization_rows_cache_runtime.py",\n',
    "",
    label="architecture runtime baseline",
)
write(path, text)


# The old installed runtime module is now redundant.
runtime_path = ROOT / "src/picture_capture/layout_visualization_rows_cache_runtime.py"
if not runtime_path.exists():
    raise SystemExit("rows-cache runtime module missing before Phase 5H deletion")
runtime_path.unlink()


# Migrate the source-shape test to the internal implementation and assert the
# public entry owns capture routing.
path = "tests/test_processing_layout_roles.py"
text = read(path)
text = replace_once(
    text,
    "def test_layout_visualization_shares_processing_understanding_entrypoint() -> None:\n"
    "    source = inspect.getsource(layout_visualization_shared.shared_snapshot_for_app)\n\n"
    "    assert \"_understand_page_current(\" in source\n"
    "    assert \"remember_visualized_understanding\" not in source\n",
    "def test_layout_visualization_shares_processing_understanding_entrypoint() -> None:\n"
    "    impl = inspect.getsource(layout_visualization_shared._shared_snapshot_for_app_impl)\n"
    "    public = inspect.getsource(layout_visualization_shared.shared_snapshot_for_app)\n\n"
    "    assert \"_understand_page_current(\" in impl\n"
    "    assert \"remember_visualized_understanding\" not in impl\n"
    "    assert \"capture_layout_rows(\" in public\n"
    "    assert \"_shared_snapshot_for_app_impl(app)\" in public\n",
    label="processing layout source-shape test",
)
write(path, text)


# Focused behavior tests for exact historical wrapper semantics.
path = ROOT / "tests/test_layout_visualization_rows_capture.py"
path.write_text('''from __future__ import annotations\n\nfrom contextlib import contextmanager\nfrom pathlib import Path\nfrom types import SimpleNamespace\n\nimport picture_capture.layout_visualization_shared as shared\n\n\ndef test_shared_snapshot_seeds_layoutrows_with_persisted_app_settings(monkeypatch, tmp_path):\n    page = tmp_path / "000003.png"\n    page.write_bytes(b"page")\n    settings = object()\n    app = SimpleNamespace(\n        project=SimpleNamespace(root=tmp_path, images=[page]),\n        current_index=0,\n        settings=settings,\n    )\n    events: list[object] = []\n\n    @contextmanager\n    def fake_capture(project_root, image_path, page_index, captured_settings):\n        events.append((Path(project_root), Path(image_path), page_index, captured_settings))\n        events.append("enter")\n        try:\n            yield\n        finally:\n            events.append("exit")\n\n    monkeypatch.setattr(shared, "capture_layout_rows", fake_capture)\n    monkeypatch.setattr(\n        shared, "_shared_snapshot_for_app_impl", lambda value: events.append(("impl", value)) or "snapshot"\n    )\n\n    assert shared.shared_snapshot_for_app(app) == "snapshot"\n    assert events == [\n        (tmp_path, page, 0, settings),\n        "enter",\n        ("impl", app),\n        "exit",\n    ]\n\n\ndef test_shared_snapshot_capture_fallbacks_preserve_historical_control_flow(monkeypatch, tmp_path):\n    calls: list[object] = []\n\n    @contextmanager\n    def forbidden_capture(*args, **kwargs):\n        raise AssertionError("capture must not start for invalid visualization context")\n        yield\n\n    monkeypatch.setattr(shared, "capture_layout_rows", forbidden_capture)\n    monkeypatch.setattr(\n        shared, "_shared_snapshot_for_app_impl", lambda app: calls.append(app) or "fallback"\n    )\n\n    no_project = SimpleNamespace(project=None)\n    assert shared.shared_snapshot_for_app(no_project) == "fallback"\n\n    invalid_index = SimpleNamespace(\n        project=SimpleNamespace(root=tmp_path, images=[]), current_index=8, settings=object()\n    )\n    assert shared.shared_snapshot_for_app(invalid_index) == "fallback"\n\n    no_settings = SimpleNamespace(\n        project=SimpleNamespace(root=tmp_path, images=[tmp_path / "x.png"]),\n        current_index=0,\n        settings=None,\n    )\n    assert shared.shared_snapshot_for_app(no_settings) == "fallback"\n    assert calls == [no_project, invalid_index, no_settings]\n\n\ndef test_phase5h_source_shape_keeps_later_visualization_decorators_and_removes_runtime():\n    root = Path(__file__).resolve().parents[1]\n    package = root / "src" / "picture_capture"\n    gui = (package / "bootstrap" / "gui.py").read_text(encoding="utf-8")\n    guard = (root / "scripts" / "architecture_guard.py").read_text(encoding="utf-8")\n\n    assert not (package / "layout_visualization_rows_cache_runtime.py").exists()\n    assert "install_layout_visualization_rows_cache" not in gui\n    assert "layout_visualization_rows_cache_runtime.py" not in guard\n    shared_pos = gui.index("install_shared_layout_visualization_source()")\n    local_pos = gui.index("install_local_indent_visualization()")\n    provenance_pos = gui.index("install_layout_role_provenance()")\n    assert shared_pos < local_pos < provenance_pos\n''', encoding="utf-8")

print("Phase 5H migration applied")
