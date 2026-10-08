from __future__ import annotations

import sys
import types
from pathlib import Path

from picture_capture.facade_compat import (
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


def test_phase9a_facades_use_one_explicit_compatibility_owner() -> None:
    helper = (ROOT / "src/picture_capture/facade_compat.py").read_text(
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
