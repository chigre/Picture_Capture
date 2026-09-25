"""Backward-compatible Windows entry point for the cross-platform OCR installer."""

from __future__ import annotations

import sys
from pathlib import Path


_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from ocr_setup import *  # noqa: F403
from ocr_setup import main


if __name__ == "__main__":
    raise SystemExit(main())
