from __future__ import annotations

"""GUI preflight for OCR actions whose visible engine selection is ineffective.

The shared OCR channel correctly treats ``Lens mode = off`` as disabled.  The
legacy quick-settings validator, however, counted the Lens checkbox alone as an
active OCR engine.  With Paddle/Tesseract unchecked this allowed an OCR action to
start even though Lens itself was disabled, after which the channel could enter
its old-project fallback policy and execute a different engine than the user had
selected.

Keep the compatibility fallback for old/non-GUI callers, but stop this ambiguous
state at the GUI action boundary.
"""

from typing import Any, Callable


def _quick_bool(app: Any, name: str, fallback: bool = False) -> bool:
    variable = dict(getattr(app, "quick_bool_vars", {})).get(name)
    if variable is not None:
        try:
            return bool(variable.get())
        except Exception:
            pass
    return bool(getattr(getattr(app, "settings", None), name, fallback))


def _quick_lens_mode(app: Any, app_module: Any) -> str:
    current = str(getattr(getattr(app, "settings", None), "paddle_lens_mode", "off") or "off")
    variable = getattr(app, "lens_mode_var", None)
    if variable is None:
        return current.strip().lower()
    try:
        visible = str(variable.get())
    except Exception:
        return current.strip().lower()
    mapping = dict(getattr(app_module, "LENS_MODE_VALUES", {}))
    return str(mapping.get(visible, visible) or "off").strip().lower()


def _ineffective_lens_only_selection(app: Any, app_module: Any) -> bool:
    paddle = _quick_bool(app, "paddle_use_paddleocr", True)
    tesseract = _quick_bool(app, "paddle_compare_tesseract", False) or bool(
        getattr(getattr(app, "settings", None), "paddle_tesseract_rescue", False)
    )
    lens_checked = _quick_bool(app, "paddle_enable_lens", False)
    lens_active = lens_checked and _quick_lens_mode(app, app_module) != "off"
    return bool(lens_checked and not lens_active and not paddle and not tesseract)


def _show_invalid_lens_selection(app: Any) -> None:
    message = (
        "当前只勾选了 Google Lens，但 Lens 运行模式仍为“关闭”。\n\n"
        "请把 Lens 模式改为 diagnostic / conflict / full，或者重新启用 PaddleOCR / Tesseract。"
        "本次 OCR 操作没有启动，避免实际运行的 OCR 与界面选择不一致。"
    )
    try:
        app.show_error("OCR 引擎配置无效", ValueError(message))
    except Exception:
        try:
            app.status_var.set(message.replace("\n", " "))
        except Exception:
            pass


def install_ocr_action_guard(app_module: Any) -> None:
    """Guard all user-facing OCR actions against Lens-checked/off ambiguity."""

    app_class = app_module.PictureCaptureApp
    if bool(getattr(app_class, "_pc_ocr_action_guard_installed", False)):
        return

    for method_name in (
        "run_ocr_draw_action",
        "run_combined_draw_action",
        "ocr_ordinary_lines_text_selected_scope",
    ):
        original = getattr(app_class, method_name, None)
        if original is None or bool(getattr(original, "_pc_ocr_action_guard", False)):
            continue

        def guarded(self, *args, __original: Callable = original, **kwargs):
            if _ineffective_lens_only_selection(self, app_module):
                _show_invalid_lens_selection(self)
                return None
            return __original(self, *args, **kwargs)

        guarded._pc_ocr_action_guard = True  # type: ignore[attr-defined]
        setattr(app_class, method_name, guarded)

    app_class._pc_ocr_action_guard_installed = True


__all__ = [
    "_ineffective_lens_only_selection",
    "install_ocr_action_guard",
]
