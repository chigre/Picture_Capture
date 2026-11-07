"""Historic training exporter path; one live module owned by training/.

No copy of mutable monkeypatch globals, ZIP state or exported functions.
Bare picture_capture package import remains metadata-only.
"""
import sys as _sys
from ..training import export_runtime as _canonical

_sys.modules[__name__] = _canonical
