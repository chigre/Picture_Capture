from __future__ import annotations

from pathlib import Path

from picture_capture.ui.text_wrap import (
    _label_measure,
    _mixed_ui_wrap_tokens,
    _normalize_ui_paragraphs,
    _wrap_mixed_ui_text,
)


ROOT = Path(__file__).resolve().parents[1]


def test_mixed_ui_wrap_preserves_existing_normalization_contract() -> None:
    assert _normalize_ui_paragraphs("页面\n模板\n\n作用：测试") == "页面模板\n\n作用：测试"
    assert _normalize_ui_paragraphs("OCR\nengine") == "OCR engine"
    assert _mixed_ui_wrap_tokens("中文 OCR engine") == ["中", "文", " ", "OCR", " ", "engine"]


def test_mixed_ui_wrap_keeps_normal_latin_words_intact() -> None:
    wrapped = _wrap_mixed_ui_text(
        "先用 Profile OCR engine 验证页面，再扩大范围。",
        lambda value: len(value) * 10,
        90,
    )
    assert "Profile" in wrapped.splitlines()
    assert "engine" in wrapped
    assert "P\nr\no\nf\ni\nl\ne" not in wrapped


def test_text_wrap_module_has_no_reverse_dependency_on_app() -> None:
    source = (
        ROOT / "src" / "picture_capture" / "ui" / "text_wrap.py"
    ).read_text(encoding="utf-8")
    assert "picture_capture.app" not in source
    assert "from ..app" not in source
    assert callable(_label_measure)


def test_app_reexports_shared_helpers_for_compatibility() -> None:
    from picture_capture import app

    assert app._normalize_ui_paragraphs is _normalize_ui_paragraphs
    assert app._mixed_ui_wrap_tokens is _mixed_ui_wrap_tokens
    assert app._wrap_mixed_ui_text is _wrap_mixed_ui_text
    assert app._label_measure is _label_measure
