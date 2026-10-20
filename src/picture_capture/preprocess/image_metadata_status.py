"""Read and format scanned image dimensions and embedded resolution."""
from __future__ import annotations

from typing import Any


def image_dpi(info: dict[str, Any]) -> tuple[float, float] | None:
    """Return actual embedded DPI, never assume a default resolution."""
    dpi = info.get("dpi")
    if isinstance(dpi, (tuple, list)) and len(dpi) >= 2:
        try:
            x, y = float(dpi[0]), float(dpi[1])
            if 0 < x < 100000 and 0 < y < 100000:
                return x, y
        except (TypeError, ValueError, OverflowError):
            pass
    elif isinstance(dpi, (int, float)) and 0 < dpi < 100000:
        return float(dpi), float(dpi)
    return None


def image_status(width: int, height: int, dpi: tuple[float, float] | None) -> str:
    """Only dimensions belong in the main status bar; retain DPI metadata internally."""
    return f"{width}×{height} px"
