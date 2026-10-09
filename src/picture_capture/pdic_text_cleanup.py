"""Clear PDIC word text without changing its marker coordinates or metadata."""
from __future__ import annotations

from pathlib import Path

from .formats import read_pdic, read_text_detected, write_text_atomic


def clear_pdic_words(path: Path) -> int:
    """Atomically erase word fields, preserving all other PDIC columns.

    Validate the complete source before writing: malformed input must not be
    silently corrupted by a destructive bulk action.
    """
    path = Path(path)
    if not path.is_file():
        return 0
    entries = read_pdic(path)
    text, _encoding = read_text_detected(path)
    changed = sum(bool(entry.word) for entry in entries)
    if not changed:
        return 0
    lines = text.splitlines(keepends=True)
    output = []
    for line in lines:
        if not line.strip():
            output.append(line)
            continue
        prefix, separator, suffix = line.partition("#")
        if not separator:
            raise ValueError(f"{path.name}: PDIC record has no separator")
        output.append(separator + suffix)
    write_text_atomic(path, "".join(output))
    return changed
