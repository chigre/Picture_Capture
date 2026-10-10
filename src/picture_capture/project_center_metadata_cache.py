"""Best-effort persistent card metadata; never part of project authority.

The small user-level index avoids enumerating thousands of scans on each visit.
Directory and settings stat signatures invalidate the fast path; manual refresh
remains available for changes that a filesystem does not reflect in dir mtime.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .project_storage import settings_path
from .runtime_environment import user_config_root

VERSION = 1
FIELDS = ("full_name", "abbreviation", "image_count", "last_edited",
          "cover_path", "preview_path", "cover_source")


def _path() -> Path:
    return user_config_root() / "project_center_metadata.json"


def _stat_signature(path: Path) -> list[int] | None:
    try:
        stat = path.stat()
        return [stat.st_mtime_ns, stat.st_size]
    except OSError:
        return None


def identity(root: Path) -> dict[str, object]:
    return {
        "root": _stat_signature(root),
        "settings": _stat_signature(settings_path(root)),
        "qt": _stat_signature(settings_path(root).parent),
    }


def read_index() -> dict[str, Any]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("version") == VERSION:
            projects = data.get("projects")
            return projects if isinstance(projects, dict) else {}
    except (OSError, ValueError, TypeError):
        pass
    return {}


def cached_details(root: Path, index: dict[str, Any] | None = None) -> dict[str, Any] | None:
    entry = (index if index is not None else read_index()).get(str(root))
    if not isinstance(entry, dict) or entry.get("identity") != identity(root):
        return None
    detail = entry.get("detail")
    if not isinstance(detail, dict):
        return None
    if not isinstance(detail.get("image_count"), int):
        return None
    # If the cover vanished, never reuse an obsolete preview pathname.
    preview = str(detail.get("preview_path") or "")
    if preview and not Path(preview).is_file():
        return None
    return {k: detail[k] for k in FIELDS if k in detail}


def store_details(details: list[dict[str, Any]]) -> None:
    """Atomic best-effort write from the background metadata worker."""
    path = _path()
    projects = read_index()
    for detail in details:
        root = Path(str(detail.get("path") or "")).expanduser()
        if not detail.get("exists") or not root.is_dir():
            projects.pop(str(root), None)
            continue
        projects[str(root)] = {
            "identity": identity(root),
            "detail": {k: detail[k] for k in FIELDS if k in detail},
        }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=path.parent,
                prefix=".project-center-", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump({"version": VERSION, "projects": projects}, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    except OSError:
        # Read-only configuration folders must not prevent listing projects.
        pass


def clear_cached_details(root: Path) -> None:
    """Drop one cache key on explicit rescan, without touching project files."""
    projects = read_index()
    projects.pop(str(root.expanduser()), None)
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent,
            prefix=".project-center-", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump({"version": VERSION, "projects": projects}, handle, ensure_ascii=False)
        os.replace(temporary, path)
    except OSError:
        pass
