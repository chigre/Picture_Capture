"""Conservative, user-opted lazy *diagnostic-only* second OCR invocation.

Never suppress an engine that can rescue or arbitrate final entries. This
optimization only skips a Tesseract diagnostic pass on columns where Paddle
accepted every visible candidate with explicit grammar and high confidence.
It is disabled by default because a second engine can still reveal otherwise
invisible missing words on real scans.
"""
from __future__ import annotations

from typing import Any


def can_skip_tesseract_diagnostic_column(
    diagnostics: list[dict[str, Any]],
    *,
    enabled: bool,
    paddle_enabled: bool,
    tesseract_enabled: bool,
    rescue_enabled: bool,
    arbitration_enabled: bool,
    lens_mode: str,
) -> bool:
    if not (
        enabled and paddle_enabled and tesseract_enabled
        and not rescue_enabled and not arbitration_enabled
        and lens_mode == "off"
    ):
        return False
    rows = [row for row in diagnostics if isinstance(row, dict) and "meta" not in row]
    if len(rows) < 2:
        return False
    for row in rows:
        feat = row.get("features", {}) or {}
        if not isinstance(feat, dict):
            return False
        if not row.get("accepted") or row.get("needs_review"):
            return False
        try:
            confidence = float(row.get("confidence", 0.0))
        except (TypeError, ValueError, OverflowError):
            return False
        if not 0.92 <= confidence <= 1.0:
            return False
        if not (
            row.get("pos_cue") or row.get("inflection_cue")
            or feat.get("structural_cue") or feat.get("front_structure_cue")
        ):
            return False
        if row.get("alphabetical_warning") or row.get("reject_reason"):
            return False
    return True
