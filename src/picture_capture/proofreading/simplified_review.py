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

def guarded_write_records(
    page: Path, path: Path, stem: str, records: dict[str, dict],
    expected: bytes | None, *, writer=None,
) -> bytes:
    """Preserve exact human bytes via a source-pinned R3 recovery journal.

    Optimistic check + O_EXCL intent is not atomic cross-process file CAS.
    """
    from tempfile import TemporaryDirectory
    from .candidate_delete import _load_unambiguous_json
    from . import transactions as tx

    page, path = Path(page), Path(path)
    if writer is None:
        writer = write_records
    if stem != page.stem or tx._marker_present(tx._recovery_path(page)):
        raise RuntimeError("R3 存在其他事务恢复标记或页面已改变")
    if tx._bytes_or_absent(path) != expected:
        raise RuntimeError("R3 简体人工副本由其他人修改，拒绝覆盖")
    if expected is not None:
        # The UI reader tolerates corrupt legacy data for display; a writer
        # must not silently collapse duplicated human JSON or invalid data.
        try:
            original_doc = _load_unambiguous_json(expected)
        except (UnicodeError, ValueError, TypeError) as exc:
            raise RuntimeError("R3 简体人工副本不能无损解析，拒绝覆盖") from exc
        if (not isinstance(original_doc, dict)
                or original_doc.get("format") != "picture_capture_simplified_review"
                or type(original_doc.get("format_version")) is not int
                or original_doc["format_version"] != FORMAT_VERSION
                or original_doc.get("page") != stem
                or not isinstance(original_doc.get("entries"), list)):
            raise RuntimeError("R3 简体人工副本格式不可信，拒绝覆盖")

    with TemporaryDirectory(prefix="pc-r3-simplified-") as directory:
        proposal = Path(directory) / "proposal.json"
        writer(proposal, stem, records)
        target = proposal.read_bytes()
    if tx._bytes_or_absent(path) != expected:
        raise RuntimeError("R3 简体预览期间外部修改了人工副本")
    if target == expected:
        return target

    marker = tx._stage_recovery(
        page, [("simplified", expected, target)], rollback_required=True,
    )
    try:
        marker_bytes = marker.read_bytes()
        if (not tx._recovery_marker_unchanged(marker, marker_bytes)
                or tx._bytes_or_absent(path) != expected):
            raise RuntimeError("R3 简体来源或恢复意图已变化")
        tx._publish(path, target)
        if (tx._bytes_or_absent(path) != target
                or not tx._recovery_marker_unchanged(marker, marker_bytes)):
            raise RuntimeError("R3 简体保存回读或恢复意图不一致")
        marker.unlink()
        if tx._marker_present(marker):
            raise RuntimeError("R3 简体恢复标记未能清除")
    except Exception:
        if tx._marker_present(marker):
            try:
                tx._rollback_failed_publish(page)
            except (OSError, RuntimeError, ValueError):
                # An unresolved journal must quarantine subsequent writers.
                pass
        raise
    return target
