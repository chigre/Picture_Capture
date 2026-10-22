from __future__ import annotations

import sys
import types
from pathlib import Path

from picture_capture.compat import facade_mirror as facade_compat
from picture_capture.compat.facade_mirror import (
    install_core_assignment_mirror,
    publish_core_namespace,
)


ROOT = Path(__file__).resolve().parents[1]


def test_publish_core_namespace_keeps_non_dunder_surface() -> None:
    core = types.ModuleType("_phase9a_core")
    core.public = object()
    core._private = object()
    core.__hidden__ = object()
    namespace: dict[str, object] = {}

    publish_core_namespace(namespace, core)

    assert namespace["public"] is core.public
    assert namespace["_private"] is core._private
    assert "__hidden__" not in namespace


def test_assignment_mirror_matches_historical_same_named_core_contract() -> None:
    module_name = "_phase9a_facade"
    core = types.ModuleType("_phase9a_core")
    original = object()
    core.existing = original
    facade = types.ModuleType(module_name)
    sys.modules[module_name] = facade
    try:
        install_core_assignment_mirror(module_name, core)

        patched = object()
        facade.existing = patched
        assert facade.existing is patched
        assert core.existing is patched

        unrelated = object()
        facade.new_name = unrelated
        assert facade.new_name is unrelated
        assert not hasattr(core, "new_name")

        # Monkeypatch teardown is another assignment and must mirror as well.
        facade.existing = original
        assert core.existing is original

        replacement_core = object()
        facade._core = replacement_core
        assert not hasattr(core, "_core")
    finally:
        sys.modules.pop(module_name, None)


def test_assignment_mirror_registry_keeps_facades_independent() -> None:
    names = ("_phase9b_facade_a", "_phase9b_facade_b")
    cores = (types.ModuleType("_phase9b_core_a"), types.ModuleType("_phase9b_core_b"))
    facades = (types.ModuleType(names[0]), types.ModuleType(names[1]))
    for core, value in zip(cores, ("a", "b")):
        core.existing = value
    for name, facade in zip(names, facades):
        sys.modules[name] = facade
    try:
        install_core_assignment_mirror(names[0], cores[0])
        install_core_assignment_mirror(names[1], cores[1])

        facades[0].existing = "patched-a"
        assert cores[0].existing == "patched-a"
        assert cores[1].existing == "b"

        facades[1].existing = "patched-b"
        assert cores[0].existing == "patched-a"
        assert cores[1].existing == "patched-b"
        assert facades[0].__class__ is facades[1].__class__
    finally:
        for name in names:
            sys.modules.pop(name, None)
            facade_compat._CORE_BY_MODULE.pop(name, None)


def test_assignment_mirror_reinstall_refreshes_registered_core() -> None:
    module_name = "_phase9b_reload_facade"
    facade = types.ModuleType(module_name)
    first = types.ModuleType("_phase9b_first_core")
    second = types.ModuleType("_phase9b_second_core")
    first.existing = "first"
    second.existing = "second"
    sys.modules[module_name] = facade
    try:
        install_core_assignment_mirror(module_name, first)
        facade.existing = "patched-first"
        assert first.existing == "patched-first"

        install_core_assignment_mirror(module_name, second)
        facade.existing = "patched-second"
        assert first.existing == "patched-first"
        assert second.existing == "patched-second"
        assert facade.__class__ is facade_compat.CoreAssignmentMirrorModule
    finally:
        sys.modules.pop(module_name, None)
        facade_compat._CORE_BY_MODULE.pop(module_name, None)


def test_phase9a_facades_use_one_explicit_compatibility_owner() -> None:
    helper = (ROOT / "src/picture_capture/compat/facade_mirror.py").read_text(
        encoding="utf-8"
    )
    assert "def publish_core_namespace(" in helper
    assert "def install_core_assignment_mirror(" in helper

    for name in ("processing.py", "paddle_headwords.py"):
        source = (ROOT / "src/picture_capture" / name).read_text(encoding="utf-8")
        assert "publish_core_namespace(globals(), _core)" in source
        assert "install_core_assignment_mirror(__name__, _core)" in source
        assert "vars(_core).items()" not in source
        assert "class _CoreProxyModule" not in source
        assert "sys.modules[__name__].__class__" not in source


def test_facade_mirror_is_package_owned_without_a_root_shim() -> None:
    import importlib.util

    assert not (ROOT / "src/picture_capture/facade_compat.py").exists()
    assert importlib.util.find_spec("picture_capture.facade_compat") is None
    owner = ROOT / "src/picture_capture/compat/facade_mirror.py"
    assert owner.is_file()
    for module in ("processing.py", "paddle_headwords.py"):
        source = (ROOT / "src/picture_capture" / module).read_text(encoding="utf-8")
        assert "from .compat.facade_mirror import " in source
        assert "from .facade_compat import " not in source


def test_canonical_facade_mirror_imports_without_gui() -> None:
    import subprocess

    script = (
        "import sys; "
        "from picture_capture.compat import facade_mirror; "
        "assert callable(facade_mirror.publish_core_namespace); "
        "assert callable(facade_mirror.install_core_assignment_mirror); "
        "assert 'picture_capture.app' not in sys.modules; "
        "assert 'tkinter' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
