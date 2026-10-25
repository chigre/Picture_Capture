from __future__ import annotations

"""Shared OCR engine-selection policy, independent of execution and storage.

The public OCR channel retains its historical OcrChannelPlan dataclass/pickle
identity. Its engine aliases, ordering and plan factory are passed on every
call, so monkeypatches on the public channel remain observable. This module
never initializes Paddle, Lens, Tk, or project storage.
"""

from typing import Any
from ..models import AppSettings


def resolve_plan(
    settings: AppSettings,
    *,
    normalized_engine_name: Any,
    engine_order: tuple[str, ...],
    plan_type: Any,
) -> Any:
    """Resolve enabled and voting engines from multi-engine/legacy settings."""
    enabled: list[str] = []
    if bool(getattr(settings, "paddle_use_paddleocr", True)):
        enabled.append("paddle")
    if bool(
        getattr(settings, "paddle_compare_tesseract", False)
        or getattr(settings, "paddle_tesseract_rescue", False)
    ):
        enabled.append("tesseract")

    lens_mode = str(getattr(settings, "paddle_lens_mode", "off") or "off").strip().lower()
    if lens_mode not in {"off", "diagnostic", "conflict", "full"}:
        lens_mode = "conflict"
    lens_enabled = bool(getattr(settings, "paddle_enable_lens", False)) and lens_mode != "off"
    if lens_enabled:
        enabled.append("lens")
    else:
        lens_mode = "off"

    if not enabled:
        legacy = normalized_engine_name(getattr(settings, "ocr_engine", ""))
        enabled.append(legacy or "tesseract")
        if enabled[0] == "lens":
            # A legacy Lens-only project has no separate mode setting. Treat it
            # as a normal participating OCR rather than a diagnostic observer.
            lens_mode = "full"

    enabled = [name for name in engine_order if name in set(enabled)]
    voting = [
        name for name in enabled
        if not (name == "lens" and lens_mode == "diagnostic")
    ]
    return plan_type(
        enabled_engines=tuple(enabled),
        voting_engines=tuple(voting),
        lens_mode=lens_mode,
    )
