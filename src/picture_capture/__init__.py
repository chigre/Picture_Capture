"""Picture Capture, restored from the 2016 VB.NET project."""

__version__ = "2.14.2"

__all__ = ["__version__"]

# Retired core module imports are redirected lazily, not loaded at startup.
from .compat.legacy_module_alias import install_legacy_aliases as _install_legacy_aliases
_install_legacy_aliases()
del _install_legacy_aliases
