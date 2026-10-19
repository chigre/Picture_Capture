from __future__ import annotations

"""OCR-independent quick-setting helper for ordinary drawing/cropping paths.

The main window intentionally shares one compact parameter form across drawing
modes.  Its historical ``apply_quick_settings`` validator therefore enforces
"at least one OCR engine" even when the user clicks 【普通画线】.  That conflicts
with the current architecture: ordinary drawing consumes Layout Core roles and
is specifically the fallback when OCR is unavailable.

This adapter preserves every other quick-setting validation.  Only when all
visible OCR engines are off does it temporarily satisfy the legacy validator,
then immediately restore the user's all-off OCR selection *before* ordinary
settings are persisted or the detection worker is started.
"""

from typing import Any


def _quick_engine_values(app: Any) -> tuple[bool, bool, bool]:
    values: list[bool] = []
    variables = dict(getattr(app, "quick_bool_vars", {}))
    settings = getattr(app, "settings", None)
    for name, fallback in (
        ("paddle_use_paddleocr", True),
        ("paddle_compare_tesseract", False),
        ("paddle_enable_lens", False),
    ):
        variable = variables.get(name)
        if variable is not None:
            try:
                values.append(bool(variable.get()))
                continue
            except Exception:
                pass
        values.append(bool(getattr(settings, name, fallback)))
    return values[0], values[1], values[2]


def _apply_quick_settings_for_ordinary(app: Any) -> bool:
    """Run normal quick validation without inventing a persistent OCR engine."""

    paddle, tesseract, lens = _quick_engine_values(app)
    if paddle or tesseract or lens:
        return bool(app.apply_quick_settings(show_status=False))

    paddle_var = dict(getattr(app, "quick_bool_vars", {})).get(
        "paddle_use_paddleocr"
    )
    if paddle_var is None:
        # A normal GUI always has this variable. Keep unusual callers safe by
        # falling back to the original validator rather than mutating settings
        # behind their back.
        return bool(app.apply_quick_settings(show_status=False))

    settings = getattr(app, "settings", None)
    try:
        # Satisfy only the legacy OCR-presence check. The ordinary action never
        # consumes this temporary engine choice.
        paddle_var.set(True)
        accepted = bool(app.apply_quick_settings(show_status=False))
    finally:
        # The controls are authoritative here: a user may have just unchecked
        # Paddle while settings still contains the previous True value. Restore
        # the values captured from the visible UI, not the stale model value.
        if settings is not None:
            settings.paddle_use_paddleocr = paddle
            settings.paddle_compare_tesseract = tesseract
            settings.paddle_enable_lens = lens
        try:
            paddle_var.set(paddle)
        except Exception:
            pass
        try:
            app.sync_quick_settings()
        except Exception:
            pass
    return accepted


__all__ = ["_apply_quick_settings_for_ordinary"]
