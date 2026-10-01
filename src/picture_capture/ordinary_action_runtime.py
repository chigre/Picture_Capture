from __future__ import annotations

"""Keep the OCR-free ordinary drawing entry path independent from OCR setup.

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
        # A normal GUI always has this variable.  Keep unusual callers safe by
        # falling back to the original validator rather than mutating settings
        # behind their back.
        return bool(app.apply_quick_settings(show_status=False))

    settings = getattr(app, "settings", None)
    original_setting = bool(getattr(settings, "paddle_use_paddleocr", False))
    try:
        paddle_var.set(True)
        accepted = bool(app.apply_quick_settings(show_status=False))
    finally:
        # ``persist`` defaults to False, so the temporary value has not reached
        # settings.json. Restore both the model and control before the caller's
        # ordinary action saves its actual configuration.
        if settings is not None:
            settings.paddle_use_paddleocr = original_setting
        try:
            paddle_var.set(False)
        except Exception:
            pass
        try:
            app.sync_quick_settings()
        except Exception:
            pass
    return accepted


def install_ordinary_action_runtime(app_module: Any) -> None:
    """Route 【普通画线】 through OCR-independent quick-setting validation."""

    app_class = app_module.PictureCaptureApp
    if bool(getattr(app_class, "_pc_ordinary_action_runtime_installed", False)):
        return

    def run_normal_draw_action(self) -> None:
        if not self.guard() or not _apply_quick_settings_for_ordinary(self):
            return
        try:
            indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围无效", exc)
            return
        self.settings.detection_method = "left_edge"
        self.save_settings()
        self._detect_pages(indices, method="left_edge", force_refresh=False)

    app_class.run_normal_draw_action = run_normal_draw_action
    app_class._pc_ordinary_action_runtime_installed = True


__all__ = [
    "_apply_quick_settings_for_ordinary",
    "install_ordinary_action_runtime",
]
