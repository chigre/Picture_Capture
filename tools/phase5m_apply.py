from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "picture_capture"
OLD = PACKAGE / "unicode_nonbmp_input_runtime.py"
NEW = PACKAGE / "unicode_nonbmp_input.py"
APP = PACKAGE / "app.py"
GUI = PACKAGE / "bootstrap" / "gui.py"
GUARD = ROOT / "scripts" / "architecture_guard.py"
TEST = ROOT / "tests" / "test_unicode_nonbmp_input_runtime.py"


def replace_exact(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected marker not found in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def migrate_module() -> None:
    if not OLD.exists():
        raise SystemExit(f"missing runtime module: {OLD}")
    if NEW.exists():
        raise SystemExit(f"target already exists: {NEW}")
    OLD.rename(NEW)

    text = NEW.read_text(encoding="utf-8")
    start = text.find("def install_nonbmp_unicode_input(app_module: Any) -> None:\n")
    if start < 0:
        raise SystemExit("non-BMP installer not found")
    tail = '''def attach_nonbmp_unicode_input(app: Any) -> Any | None:\n    """Attach the Windows/Tk 8 compatibility bridge after app initialization."""\n    existing = getattr(app, "_pc_nonbmp_unicode_bridge", None)\n    if existing is not None:\n        return existing\n\n    app._pc_nonbmp_unicode_bridge = None\n    if not _needs_windows_tk8_bridge(app):\n        return None\n    try:\n        bridge = _WindowsNonBmpBridge(app)\n    except Exception:\n        return None\n    app._pc_nonbmp_unicode_bridge = bridge\n    return bridge\n\n\ndef close_nonbmp_unicode_input(app: Any) -> None:\n    """Close and detach the app-level compatibility bridge if one is active."""\n    bridge = getattr(app, "_pc_nonbmp_unicode_bridge", None)\n    if bridge is None:\n        return\n    try:\n        bridge.close()\n    except Exception:\n        pass\n    finally:\n        app._pc_nonbmp_unicode_bridge = None\n\n\n__all__ = [\n    "NativeCommit",\n    "TextSnapshot",\n    "attach_nonbmp_unicode_input",\n    "close_nonbmp_unicode_input",\n    "contains_non_bmp",\n    "legacy_tk_renderings",\n    "plan_non_bmp_repair",\n]\n'''
    NEW.write_text(text[:start] + tail, encoding="utf-8")


def migrate_app() -> None:
    text = APP.read_text(encoding="utf-8")
    import_marker = "from .text_encoding import read_text_detected\n"
    import_line = (
        "from .unicode_nonbmp_input import (\n"
        "    attach_nonbmp_unicode_input, close_nonbmp_unicode_input,\n"
        ")\n"
    )
    if import_marker not in text:
        raise SystemExit("app import marker not found")
    text = text.replace(import_marker, import_marker + import_line, 1)

    tree = ast.parse(text)
    classes = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PictureCaptureApp"
    ]
    if len(classes) != 1:
        raise SystemExit(f"expected one PictureCaptureApp, got {len(classes)}")
    app_class = classes[0]
    methods = {
        node.name: node
        for node in app_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    init = methods.get("__init__")
    if init is None or init.end_lineno is None:
        raise SystemExit("PictureCaptureApp.__init__ not found")
    if "destroy" in methods:
        raise SystemExit("PictureCaptureApp already owns destroy; reassess Phase 5M")

    lines = text.splitlines(keepends=True)
    insertion = (
        "        attach_nonbmp_unicode_input(self)\n"
        "\n"
        "    def destroy(self) -> None:\n"
        "        close_nonbmp_unicode_input(self)\n"
        "        super().destroy()\n"
        "\n"
    )
    lines[init.end_lineno:init.end_lineno] = [insertion]
    APP.write_text("".join(lines), encoding="utf-8")


def migrate_bootstrap_and_guard() -> None:
    replace_exact(
        GUI,
        "    from ..unicode_nonbmp_input_runtime import install_nonbmp_unicode_input\n",
        "",
    )
    block = (
        "    # Windows/Tk 8.6 can corrupt supplementary-plane characters (CJK Ext-B,\n"
        "    # emoji, etc.) during direct IME/key input even though Python/UTF-8 storage is\n"
        "    # sound. Install one app-level native Unicode bridge before GUI instances are\n"
        "    # created; Tk 9 and non-Windows platforms remain untouched.\n"
        "    install_nonbmp_unicode_input(app_module)\n\n"
    )
    replace_exact(GUI, block, "")
    replace_exact(GUARD, '    "unicode_nonbmp_input_runtime.py",\n', "")


def migrate_tests() -> None:
    text = TEST.read_text(encoding="utf-8")
    text = text.replace(
        "from pathlib import Path\n\nfrom picture_capture.unicode_nonbmp_input_runtime import (\n",
        "import ast\nfrom pathlib import Path\nfrom types import SimpleNamespace\n\n"
        "import picture_capture.unicode_nonbmp_input as nonbmp\n"
        "from picture_capture.unicode_nonbmp_input import (\n"
        "    attach_nonbmp_unicode_input,\n"
        "    close_nonbmp_unicode_input,\n",
        1,
    )
    old = '''def test_gui_composition_installs_nonbmp_bridge_before_app_instances_exist():\n    root = Path(__file__).resolve().parents[1]\n    source = (\n        root / "src" / "picture_capture" / "bootstrap" / "gui.py"\n    ).read_text(encoding="utf-8")\n    assert "install_nonbmp_unicode_input" in source\n    assert "install_nonbmp_unicode_input(app_module)" in source\n    assert source.index("install_nonbmp_unicode_input(app_module)") < source.index(\n        "_PREPARED_APP_MODULE = app_module"\n    )\n'''
    new = '''def test_bridge_requirement_is_windows_tk8_only(monkeypatch):\n    class TkProxy:\n        def __init__(self, patchlevel: str) -> None:\n            self.patchlevel = patchlevel\n\n        def call(self, *args):\n            assert args == ("info", "patchlevel")\n            return self.patchlevel\n\n    monkeypatch.setattr(nonbmp.platform, "system", lambda: "Linux")\n    assert not nonbmp._needs_windows_tk8_bridge(SimpleNamespace(tk=TkProxy("8.6.14")))\n\n    monkeypatch.setattr(nonbmp.platform, "system", lambda: "Windows")\n    assert nonbmp._needs_windows_tk8_bridge(SimpleNamespace(tk=TkProxy("8.6.14")))\n    assert not nonbmp._needs_windows_tk8_bridge(SimpleNamespace(tk=TkProxy("9.0.0")))\n\n\ndef test_attach_is_noop_when_bridge_not_required(monkeypatch):\n    app = SimpleNamespace()\n    monkeypatch.setattr(nonbmp, "_needs_windows_tk8_bridge", lambda _app: False)\n    assert attach_nonbmp_unicode_input(app) is None\n    assert app._pc_nonbmp_unicode_bridge is None\n\n\ndef test_attach_once_and_close_are_explicit_and_idempotent(monkeypatch):\n    events = []\n\n    class Bridge:\n        def __init__(self, app) -> None:\n            events.append(("attach", app))\n            self.closed = 0\n\n        def close(self) -> None:\n            self.closed += 1\n            events.append(("close", self.closed))\n\n    app = SimpleNamespace()\n    monkeypatch.setattr(nonbmp, "_needs_windows_tk8_bridge", lambda _app: True)\n    monkeypatch.setattr(nonbmp, "_WindowsNonBmpBridge", Bridge)\n\n    first = attach_nonbmp_unicode_input(app)\n    second = attach_nonbmp_unicode_input(app)\n    assert first is second\n    assert [kind for kind, _value in events] == ["attach"]\n\n    close_nonbmp_unicode_input(app)\n    close_nonbmp_unicode_input(app)\n    assert first.closed == 1\n    assert app._pc_nonbmp_unicode_bridge is None\n    assert [kind for kind, _value in events] == ["attach", "close"]\n\n\ndef test_app_owns_nonbmp_bridge_lifecycle_without_gui_installer():\n    root = Path(__file__).resolve().parents[1]\n    package = root / "src" / "picture_capture"\n    app_source = (package / "app.py").read_text(encoding="utf-8")\n    gui_source = (package / "bootstrap" / "gui.py").read_text(encoding="utf-8")\n    guard = (root / "scripts" / "architecture_guard.py").read_text(encoding="utf-8")\n\n    assert not (package / "unicode_nonbmp_input_runtime.py").exists()\n    assert (package / "unicode_nonbmp_input.py").exists()\n    assert "install_nonbmp_unicode_input" not in gui_source\n    assert '"unicode_nonbmp_input_runtime.py"' not in guard\n\n    tree = ast.parse(app_source)\n    app_class = next(\n        node for node in tree.body\n        if isinstance(node, ast.ClassDef) and node.name == "PictureCaptureApp"\n    )\n    methods = {\n        node.name: node\n        for node in app_class.body\n        if isinstance(node, ast.FunctionDef)\n    }\n    init_text = ast.get_source_segment(app_source, methods["__init__"]) or ""\n    destroy_text = ast.get_source_segment(app_source, methods["destroy"]) or ""\n    assert "attach_nonbmp_unicode_input(self)" in init_text\n    assert init_text.rstrip().endswith("attach_nonbmp_unicode_input(self)")\n    assert "close_nonbmp_unicode_input(self)" in destroy_text\n    assert "super().destroy()" in destroy_text\n    assert destroy_text.index("close_nonbmp_unicode_input(self)") < destroy_text.index(\n        "super().destroy()"\n    )\n'''
    if old not in text:
        raise SystemExit("old non-BMP bootstrap source-shape test not found")
    TEST.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    migrate_module()
    migrate_app()
    migrate_bootstrap_and_guard()
    migrate_tests()
    print("Phase 5M migration applied")


if __name__ == "__main__":
    main()
