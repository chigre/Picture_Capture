from __future__ import annotations

"""Atomic publish helpers used by processing crop/export paths."""

import os
from pathlib import Path
import uuid


def _publish_temp_path(target: Path) -> Path:
    """Return a same-filesystem temporary path for one eventual atomic publish."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")


def _publish_file_transaction(
    replacements: list[tuple[Path, Path]], *, stale_paths: list[Path] | None = None,
) -> None:
    """Publish a page file set together and restore the previous set on failure."""
    pairs = [(Path(temp), Path(target)) for temp, target in replacements]
    token = uuid.uuid4().hex
    old_candidates: list[Path] = []
    seen: set[str] = set()
    for path in [*(target for _temp, target in pairs), *(stale_paths or [])]:
        key = os.fspath(path)
        if key in seen:
            continue
        seen.add(key)
        old_candidates.append(path)

    backups: list[tuple[Path, Path]] = []
    published: list[Path] = []
    preserve_backups = False
    try:
        for target in old_candidates:
            if not target.exists():
                continue
            backup = target.with_name(f".{target.name}.{token}.bak")
            backup.unlink(missing_ok=True)
            os.replace(target, backup)
            backups.append((target, backup))

        for temp, target in pairs:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temp, target)
            published.append(target)
    except Exception:
        for target in reversed(published):
            target.unlink(missing_ok=True)
        restore_error: Exception | None = None
        for target, backup in reversed(backups):
            if not backup.exists():
                continue
            try:
                os.replace(backup, target)
            except Exception as exc:
                restore_error = restore_error or exc
        if restore_error is not None:
            preserve_backups = True
            raise RuntimeError(
                "切图发布失败，且回滚旧文件时发生错误；已保留隐藏 .bak 恢复副本。"
            ) from restore_error
        raise
    finally:
        for temp, _target in pairs:
            temp.unlink(missing_ok=True)
        if not preserve_backups:
            for _target, backup in backups:
                backup.unlink(missing_ok=True)
