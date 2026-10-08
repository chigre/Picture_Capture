from __future__ import annotations

"""Explicit owner for historical public-facade compatibility behavior.

Two long-standing public modules expose most names from their implementation
cores and mirror assignments back into those cores.  External plugins, tests,
debug scripts and monkeypatch-based tooling may rely on that behavior, so this
module centralizes the mechanism without shrinking the compatibility surface.
"""

import sys
import types
from collections.abc import MutableMapping
from types import ModuleType
from typing import Any


def publish_core_namespace(
    namespace: MutableMapping[str, Any],
    core: ModuleType,
) -> None:
    """Publish every non-dunder core name into a historical facade namespace."""
    for name, value in vars(core).items():
        if not name.startswith("__"):
            namespace[name] = value


def install_core_assignment_mirror(module_name: str, core: ModuleType) -> None:
    """Mirror facade assignments into same-named attributes on *core*.

    The generated module subclass closes over the selected core so the two
    historical facades remain independent.  Installing the subclass through
    ModuleType.__setattr__ deliberately bypasses any previously installed
    facade proxy, which keeps module reloads safe.
    """
    module = sys.modules[module_name]

    class CoreAssignmentMirrorModule(types.ModuleType):
        def __setattr__(self, name: str, value: object) -> None:
            types.ModuleType.__setattr__(self, name, value)
            if name != "_core" and hasattr(core, name):
                setattr(core, name, value)

    types.ModuleType.__setattr__(module, "__class__", CoreAssignmentMirrorModule)


__all__ = ["install_core_assignment_mirror", "publish_core_namespace"]
