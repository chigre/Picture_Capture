from __future__ import annotations


_converter = None
_converter_error: str | None = None


def reset_converter() -> None:
    """Clear the lazy OpenCC runtime cache so the environment can be probed again."""
    global _converter, _converter_error
    _converter = None
    _converter_error = None


def _get_converter(*, retry: bool = False):
    """Return a lazily initialized official OpenCC t2s converter.

    ``retry=True`` clears a previously cached initialization failure first.  This
    matters after an in-place package migration/repair: pip metadata may already
    report OpenCC as installed while the Python module files were temporarily
    removed by uninstalling the legacy package that shared the same import name.
    """
    global _converter, _converter_error
    if retry and _converter is None and _converter_error is not None:
        _converter_error = None
    if _converter is not None:
        return _converter
    if _converter_error is not None:
        return None
    try:
        import opencc
        converter = opencc.OpenCC("t2s.json")
        # Functional smoke test: importing package metadata alone is insufficient.
        converter.convert("繁體中文")
        _converter = converter
    except Exception as exc:  # pragma: no cover - environment dependent
        _converter_error = f"{type(exc).__name__}: {exc}"
        return None
    return _converter


def opencc_runtime_status(*, retry: bool = False) -> dict[str, object]:
    """Return actual OpenCC runtime status, including initialization errors."""
    converter = _get_converter(retry=retry)
    return {
        "available": converter is not None,
        "error": None if converter is not None else (_converter_error or "未知错误"),
    }


def simplify_text(text: str) -> str | None:
    """Convert Traditional Chinese to Simplified Chinese with official OpenCC.

    ``None`` means the OpenCC runtime is unavailable (not necessarily uninstalled).
    """
    converter = _get_converter()
    if converter is None:
        return None
    return str(converter.convert(str(text)))


def simplified_display(text: str) -> str:
    """UI value for the proofreading companion field."""
    original = str(text)
    converted = simplify_text(original)
    if converted is None:
        return "OpenCC不可用"
    return "√" if converted == original else converted
