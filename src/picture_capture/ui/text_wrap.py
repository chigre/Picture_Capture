from __future__ import annotations

import re
import tkinter as tk
from tkinter import font
import unicodedata


_UI_WRAP_CLOSING_PUNCTUATION = frozenset("，。；：！？、）》】」』”’…,.!?;:)]}»")
_UI_WRAP_OPENING_PUNCTUATION = frozenset("（《【「『“‘([{«")


def _normalize_ui_paragraphs(value: object) -> str:
    """Remove accidental single hard breaks while preserving true paragraphs."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text)
    normalized: list[str] = []
    for block in blocks:
        parts = [part.strip() for part in block.split("\n") if part.strip()]
        if not parts:
            continue
        merged = parts[0]
        for part in parts[1:]:
            if (
                merged
                and part
                and merged[-1].isascii()
                and part[0].isascii()
                and (merged[-1].isalnum() or merged[-1] in "_%")
                and (part[0].isalnum() or part[0] in "_%")
            ):
                merged += " "
            merged += part
        normalized.append(re.sub(r"[ \t]+", " ", merged).strip())
    return "\n\n".join(normalized)


def _mixed_ui_wrap_tokens(paragraph: str) -> list[str]:
    """Return CJK characters as individual break opportunities; keep Latin runs whole."""
    tokens: list[str] = []
    ascii_run: list[str] = []

    def flush_ascii() -> None:
        if ascii_run:
            tokens.append("".join(ascii_run))
            ascii_run.clear()

    for char in paragraph:
        if char.isspace():
            flush_ascii()
            if not tokens or tokens[-1] != " ":
                tokens.append(" ")
            continue
        if unicodedata.east_asian_width(char) in {"W", "F"}:
            flush_ascii()
            tokens.append(char)
            continue
        ascii_run.append(char)
    flush_ascii()
    return tokens


def _wrap_mixed_ui_text(value: object, measure, max_width: int) -> str:
    """Pixel-wrap Chinese/Latin UI prose without relying on Tk word boundaries.

    Tk font.measure() crosses the Python/Tcl boundary and is comparatively
    expensive on Windows. Measure each token/character once and accumulate
    widths instead of repeatedly measuring an ever-growing line prefix.
    """
    text = _normalize_ui_paragraphs(value)
    limit = max(24, int(max_width))
    if not text:
        return ""

    width_cache: dict[str, int] = {}

    def width(piece: str) -> int:
        cached = width_cache.get(piece)
        if cached is None:
            cached = int(measure(piece))
            width_cache[piece] = cached
        return cached

    space_width = width(" ")
    wrapped_paragraphs: list[str] = []
    for paragraph in text.split("\n\n"):
        lines: list[str] = []
        current = ""
        current_width = 0
        pending_space = False

        def flush_current() -> None:
            nonlocal current, current_width
            if current:
                lines.append(current.rstrip())
                current = ""
                current_width = 0

        for token in _mixed_ui_wrap_tokens(paragraph):
            if token == " ":
                pending_space = bool(current)
                continue
            prefix = " " if pending_space and current else ""
            token_width = width(token)
            candidate_width = current_width + (space_width if prefix else 0) + token_width
            if not current or candidate_width <= limit:
                current += prefix + token
                current_width = candidate_width
                pending_space = False
                continue

            if token in _UI_WRAP_CLOSING_PUNCTUATION:
                current += token
                current_width += token_width
                flush_current()
                pending_space = False
                continue

            if current and current[-1] in _UI_WRAP_OPENING_PUNCTUATION:
                opening = current[-1]
                current = current[:-1].rstrip()
                current_width = max(0, current_width - width(opening))
                flush_current()
                current = opening + token
                current_width = width(opening) + token_width
                pending_space = False
                continue

            flush_current()
            token = token.lstrip()
            token_width = width(token)
            if token_width <= limit:
                current = token
                current_width = token_width
            else:
                # Extremely long Latin/URL-like tokens are the only case where
                # a word may be split; normal English words stay intact.
                for char in token:
                    char_width = width(char)
                    if current and current_width + char_width > limit:
                        flush_current()
                    current += char
                    current_width += char_width
            pending_space = False
        flush_current()
        wrapped_paragraphs.append("\n".join(lines))
    return "\n\n".join(wrapped_paragraphs)


def _label_measure(label: tk.Misc):
    """Return a Tk font measurement callable for classic or ttk labels."""
    try:
        font_spec = str(label.cget("font") or "").strip()
        if font_spec:
            return font.Font(font=font_spec).measure
    except (tk.TclError, TypeError, ValueError):
        pass
    return font.nametofont("TkDefaultFont").measure


__all__ = [
    "_label_measure",
    "_mixed_ui_wrap_tokens",
    "_normalize_ui_paragraphs",
    "_wrap_mixed_ui_text",
]
