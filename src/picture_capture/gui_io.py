from __future__ import annotations

"""Static application-facing PDIC I/O composition.

Core composition may wrap ``formats.read_pdic`` and ``formats.write_pdic`` with
classification sidecar persistence. The GUI additionally captures the first
automatic PDIC result as a training baseline. Resolve the core-owned callables
at call time so application imports do not depend on bootstrap mutating
``formats`` before ``app.py`` imports them by value.
"""

from pathlib import Path

from . import formats as _formats
from .models import Entry
from .training_baseline import build_write_pdic_capture


pdic_path = _formats.pdic_path
read_ppp = _formats.read_ppp
write_ppp = _formats.write_ppp
write_text_atomic = _formats.write_text_atomic


def read_pdic(path: Path) -> list[Entry]:
    """Read PDIC through the current core-composed formats boundary."""
    return _formats.read_pdic(path)


def _write_current_pdic(
    path: Path,
    entries: list[Entry],
    image_width: int,
    pages: tuple[str, str, str],
) -> bool:
    return _formats.write_pdic(path, entries, image_width, pages)


write_pdic = build_write_pdic_capture(_write_current_pdic)


__all__ = [
    "pdic_path",
    "read_pdic",
    "read_ppp",
    "write_pdic",
    "write_ppp",
    "write_text_atomic",
]
