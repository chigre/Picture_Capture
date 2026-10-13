from __future__ import annotations

"""Crash-recoverable, per-page crop publication.

A journal is written before any existing output is moved aside. A committed
marker separates rollback from cleanup so an interrupted publish is recoverable
without guessing which of several output files is authoritative.
"""

import json
import os
from pathlib import Path
import uuid


def _publish_temp_path(target: Path) -> Path:
    """Return a same-filesystem temporary path for one eventual atomic publish."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")


def _journal_path(parent: Path, token: str, state: str = "pending") -> Path:
    return parent / f".crop-publish-{token}.{state}.json"


def _write_journal(path: Path, payload: dict) -> None:
    temp = _publish_temp_path(path)
    try:
        with temp.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _recover_journal(journal: Path, *, allowed_root: Path | None = None) -> None:
    payload = json.loads(journal.read_text(encoding="utf-8"))
    if payload.get("version") != 1:
        raise ValueError(f"Unsupported crop transaction: {journal}")
    originals = [(Path(item["target"]), Path(item["backup"]), bool(item["existed"]))
                 for item in payload["originals"]]
    staged = [Path(path) for path in payload["staged"]]
    paths = [path for pair in originals for path in pair[:2]] + staged
    if allowed_root is not None:
        boundary = allowed_root.resolve()
        if any(not path.resolve().is_relative_to(boundary) for path in paths):
            raise ValueError(f"Crop journal refers outside its project: {journal}")
    if ".committed." not in journal.name:
        # Roll back a transaction that never received the durable commit marker.
        for target, backup, existed in reversed(originals):
            if backup.exists():
                os.replace(backup, target)
            elif not existed:
                target.unlink(missing_ok=True)
    else:
        # The full new set was published. Keep it and discard its backups.
        for _target, backup, _existed in originals:
            backup.unlink(missing_ok=True)
    for temp in staged:
        temp.unlink(missing_ok=True)
    journal.unlink(missing_ok=True)


def recover_incomplete_crop_publications(project_root: Path) -> int:
    """Recover interrupted page exports when a project is opened, before jobs start.

    Scans only the QT root and its immediate output directories, not every PNG.
    No recovery runs during a live parallel batch; other pages may be publishing.
    """
    from .project_storage import qt_root

    root = qt_root(Path(project_root))
    if not root.is_dir():
        return 0
    directories = [root, *(p for p in root.iterdir() if p.is_dir())]
    recovered = 0
    for folder in directories:
        for journal in sorted(folder.glob(".crop-publish-*.pending.json")) + sorted(
            folder.glob(".crop-publish-*.committed.json")
        ):
            _recover_journal(journal, allowed_root=root)
            recovered += 1
    return recovered


def _publish_file_transaction(
    replacements: list[tuple[Path, Path]], *, stale_paths: list[Path] | None = None,
) -> None:
    """Publish one page of files, rollback on errors, recover on next project open."""
    pairs = [(Path(temp), Path(target)) for temp, target in replacements]
    if not pairs:
        return
    token = uuid.uuid4().hex
    old_candidates: list[Path] = []
    seen: set[str] = set()
    for path in [*(target for _temp, target in pairs), *(stale_paths or [])]:
        key = os.fspath(path)
        if key not in seen:
            seen.add(key)
            old_candidates.append(path)

    originals = [
        (target, target.with_name(f".{target.name}.{token}.bak"), target.exists())
        for target in old_candidates
    ]
    journal = _journal_path(pairs[0][1].parent, token)
    committed = _journal_path(pairs[0][1].parent, token, "committed")
    payload = {
        "version": 1,
        "originals": [
            {"target": str(target.resolve()), "backup": str(backup.resolve()), "existed": existed}
            for target, backup, existed in originals
        ],
        "staged": [str(temp.resolve()) for temp, _target in pairs],
    }
    # Make journal paths absolute: reopening from another working directory is safe.
    journal.parent.mkdir(parents=True, exist_ok=True)
    _write_journal(journal, payload)
    try:
        for target, backup, existed in originals:
            if existed:
                os.replace(target, backup)
        for temp, target in pairs:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temp, target)
        os.replace(journal, committed)
    except Exception:
        # Preserve the journal and .bak files if rollback itself fails; the next
        # project open will retry. Keep the historical RuntimeError contract.
        try:
            _recover_journal(journal)
        except Exception as restore_exc:
            raise RuntimeError(
                "切图发布失败，且回滚旧文件时发生错误；已保留隐藏 .bak 恢复副本。"
            ) from restore_exc
        raise
    finally:
        if committed.exists():
            # Failed backup cleanup must leave the committed journal for recovery.
            _recover_journal(committed)
