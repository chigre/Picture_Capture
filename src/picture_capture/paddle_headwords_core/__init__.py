"""Historical PaddleOCR core path, kept for source and pickle compatibility.

The real implementation and mutable OCR state live in ocr.headword_core_runtime.
This import identity bridge is necessary because importing the bare package must
remain side-effect-free. It creates no duplicate functions, state or callbacks.
"""
import sys as _sys

from ..ocr import headword_core_runtime as _canonical

_sys.modules[__name__] = _canonical
