"""Page-local auxiliary crop boundaries, deliberately independent of PDIC.

These lines are physical partition hints and never carry Entry identity,
headword text or PDIC numbering. They are saved in a dedicated JSON sidecar.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import tempfile

from .project_storage import is_managed_project, storage_root

FORMAT = "picture-capture-auxiliary-lines-v1"


@dataclass(frozen=True)
class AuxiliaryLine:
    x: int
    y: int


def auxiliary_line_path(image_path: str | Path) -> Path:
    page = Path(image_path)
    root = page.parent
    folder = storage_root(root) / "data" if is_managed_project(root) else root / "QT"
    return folder / "AuxiliaryLines" / f"{page.stem}.json"


def read_auxiliary_lines(image_path: str | Path) -> list[AuxiliaryLine]:
    path = auxiliary_line_path(image_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        return []
    result = []
    for item in payload.get("lines", []):
        try:
            x, y = int(item["x"]), int(item["y"])
            if x >= 0 and y >= 0:
                result.append(AuxiliaryLine(x, y))
        except (TypeError, ValueError, KeyError):
            continue
    return result


def write_auxiliary_lines(image_path: str | Path, lines) -> Path:
    path = auxiliary_line_path(image_path)
    payload = {
        "format": FORMAT,
        "lines": [{"x": int(line.x), "y": int(line.y)} for line in lines],
    }
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path


class AuxiliaryLineEdits:
    """Small undoable state machine shared by click/drag/delete UI actions."""

    def __init__(self, lines=()):
        self.lines = list(lines)
        self._history: list[list[AuxiliaryLine]] = []

    def snapshot(self):
        self._history.append(list(self.lines))
        if len(self._history) > 100:
            self._history.pop(0)

    def add(self, line: AuxiliaryLine):
        self.snapshot()
        self.lines.append(line)

    def move(self, index: int, line: AuxiliaryLine):
        if not (0 <= index < len(self.lines)):
            return False
        self.snapshot()
        self.lines[index] = line
        return True

    def delete(self, index: int):
        if not (0 <= index < len(self.lines)):
            return False
        self.snapshot()
        self.lines.pop(index)
        return True

    def undo(self):
        if not self._history:
            return False
        self.lines = self._history.pop()
        return True
