from __future__ import annotations

"""Persistence helpers for editable simplified headwords in the review UI.

PDIC is deliberately left unchanged because several downstream workflows depend
on its historical 8-field text format.  The review companion therefore uses a
small per-page JSON sidecar keyed primarily by the stable marker coordinates.
"""

from pathlib import Path
import json


FORMAT_VERSION = 1


def entry_key(x: int, y: int) -> str:
    return f"{int(x)},{int(y)}"


def read_records(path: Path) -> dict[str, dict]:
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    rows = payload.get("entries", []) if isinstance(payload, dict) else []
    result: dict[str, dict] = {}
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            x = int(item.get("x"))
            y = int(item.get("y"))
        except (TypeError, ValueError):
            continue
        key = entry_key(x, y)
        result[key] = {
            "x": x,
            "y": y,
            "source_word": str(item.get("source_word", "")),
            "text": str(item.get("text", "")),
            "manual": bool(item.get("manual", False)),
        }
    return result


def write_records(path: Path, page: str, records: dict[str, dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for key, item in records.items():
        if not isinstance(item, dict):
            continue
        try:
            x = int(item.get("x"))
            y = int(item.get("y"))
        except (TypeError, ValueError):
            try:
                x_str, y_str = str(key).split(",", 1)
                x, y = int(x_str), int(y_str)
            except Exception:
                continue
        rows.append({
            "x": x,
            "y": y,
            "source_word": str(item.get("source_word", "")),
            "text": str(item.get("text", "")),
            "manual": bool(item.get("manual", False)),
        })
    rows.sort(key=lambda item: (int(item["y"]), int(item["x"])))
    payload = {
        "format": "picture_capture_simplified_review",
        "format_version": FORMAT_VERSION,
        "page": str(page),
        "entries": rows,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
