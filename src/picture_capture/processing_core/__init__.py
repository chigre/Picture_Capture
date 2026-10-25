"""Legacy processing core import and pickle identity bridge.

All geometry/detection/crop/spawn coordination implementations now belong to
runtime.processing_core_runtime. Re-export the SAME mutable module instance:
public processing facade patches and spawn worker pickles remain compatible.
"""
import sys as _sys
from ..runtime import processing_core_runtime as _canonical
_sys.modules[__name__] = _canonical
