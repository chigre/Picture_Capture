from __future__ import annotations

"""Static GUI preflight for ambiguous OCR engine selections.

The shared OCR channel correctly treats ``Lens mode = off`` as disabled. The
legacy quick-settings validator counts the Lens checkbox itself as an enabled
engine, so the specific state "Lens checked + mode off + no runnable local OCR"
must be rejected before the generic validator runs.

The guard is now called directly by the three user action boundaries. No
PictureCaptureApp method is patched at GUI startup.
"""

from typing import Any


LENS_MODE_LABELS = {
    "off": "① 关闭",
    "diagnostic": "② 仅诊断对照",
    "conflict": "③ 冲突/低可信时调用（推荐）",
    "full": "④ 全页参与三OCR融合",
}
LENS_MODE_VALUES = {label: value for value, label in LENS_MODE_LABELS.items()}


def _quick_bool(app: Any, name: str, fallback: bool = False) -> bool:
    variable = dict(getattr(app, "quick_bool_vars", {})).get(name)
    if variable is not None:
        try:
            return bool(variable.get())
        except Exception:
            pass
    return bool(getattr(getattr(app, "settings", None), name, fallback))


def _quick_lens_mode(app: Any, app_module: Any | None = None) -> str:
    current = str(
        getattr(getattr(app, "settings", None), "paddle_lens_mode", "off") or "off"
    )
    variable = getattr(app, "lens_mode_var", None)
    if variable is None:
        return current.strip().lower()
    try:
        visible = str(variable.get())
    except Exception:
        return current.strip().lower()

    mapping = LENS_MODE_VALUES
    if app_module is not None:
        mapping = dict(getattr(app_module, "LENS_MODE_VALUES", mapping))
    return str(mapping.get(visible, visible) or "off").strip().lower()


def _ineffective_lens_only_selection(
    app: Any,
    app_module: Any | None = None,
) -> bool:
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


def guard_ocr_action_selection(
    app: Any,
    app_module: Any | None = None,
) -> bool:
    """Return whether a user-facing OCR action may proceed."""
    if not _ineffective_lens_only_selection(app, app_module):
        return True
    _show_invalid_lens_selection(app)
    return False


def install_ocr_action_guard(app_module: Any) -> None:
    """Compatibility shim; action boundaries now invoke the guard statically."""
    _ = app_module


__all__ = [
    "LENS_MODE_LABELS",
    "LENS_MODE_VALUES",
    "_ineffective_lens_only_selection",
    "guard_ocr_action_selection",
    "install_ocr_action_guard",
]
