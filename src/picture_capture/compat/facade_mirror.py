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


_CORE_BY_MODULE: dict[str, ModuleType] = {}


class CoreAssignmentMirrorModule(types.ModuleType):
    """Stable module class that mirrors assignments into a registered core."""

    def __setattr__(self, name: str, value: object) -> None:
        core = _CORE_BY_MODULE.get(self.__name__)
        types.ModuleType.__setattr__(self, name, value)
        if core is not None and name != "_core" and hasattr(core, name):
            setattr(core, name, value)


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

    Registration is data-driven: every historical facade uses the same stable
    module class while this module owns the explicit facade-to-core mapping.
    Reinstalling a facade simply refreshes its mapping and is therefore safe
    across reloads and repeated bootstrap calls.
    """
    module = sys.modules[module_name]
    _CORE_BY_MODULE[module_name] = core
    types.ModuleType.__setattr__(module, "__class__", CoreAssignmentMirrorModule)


__all__ = ["install_core_assignment_mirror", "publish_core_namespace"]
