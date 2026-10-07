from __future__ import annotations

"""OCR text cleanup rules and legacy .OCRed text persistence."""

from pathlib import Path
import re

from .models import read_noncomment_lines


def load_replace_rules(path: Path) -> list[tuple[str, str, str]]:
    if not path.exists():
        return []
    rules: list[tuple[str, str, str]] = []
    for line in read_noncomment_lines(path):
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] in {"N", "R"}:
            rules.append((parts[0], parts[1], parts[2] if len(parts) >= 3 else ""))
    return rules


def process_ocr_text(
    text: str, rules: list[tuple[str, str, str]], lowercase: bool,
) -> str:
    text = text.replace("'", "").strip()
    nonempty = [line.strip() for line in text.splitlines() if line.strip()]
    if nonempty:
        multiword = [line for line in nonempty if len(line.split()) > 1]
        text = multiword[0] if multiword else nonempty[0]
    for kind, search, replacement in rules:
        text = (
            text.replace(search, replacement)
            if kind == "N"
            else re.sub(search, replacement, text)
        )
    return text.lower() if lowercase else text


def export_ocred(path: Path, texts: list[str]) -> None:
    path.write_text(
        "".join(f"{i:03d}|\`{text}\n" for i, text in enumerate(texts)),
        encoding="utf-8",
    )


def import_ocred(path: Path) -> list[str]:
    texts: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        texts.append(line.split("\`", 1)[1] if "\`" in line else line)
    return texts
