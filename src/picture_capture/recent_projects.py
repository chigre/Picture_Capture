"""User-level recent-project registry (never deletes project data)."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .models import project_cover_path, project_page_images
from .project_storage import settings_path
from .runtime_environment import legacy_user_config_files, user_config_root


def default_recent_projects_path() -> Path:
    return user_config_root() / "recent_projects.json"


def load_recent_projects(path: Path | None = None) -> list[dict[str, object]]:
    target = path or default_recent_projects_path()
    candidates = (target,) if path is not None else (
        target, *legacy_user_config_files("recent_projects.json")
    )
    for candidate in candidates:
        try:
            value = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict) and row.get("path")]
        except (OSError, ValueError, TypeError):
            continue
    return []


def save_recent_projects(rows: list[dict[str, object]], path: Path | None = None) -> None:
    target = path or default_recent_projects_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, target)


def touch_recent_project(
    root: Path,
    path: Path | None = None,
    *,
    last_page: str | None = None,
    last_page_index: int | None = None,
) -> list[dict[str, object]]:
    """Move a project to the front while preserving its per-project resume state."""
    resolved = root.expanduser().resolve()
    existing: dict[str, object] = {}
    remaining: list[dict[str, object]] = []
    for row in load_recent_projects(path):
        if Path(str(row["path"])).expanduser() == resolved:
            existing = dict(row)
        else:
            remaining.append(row)
    row: dict[str, object] = {
        **existing,
        "name": resolved.name,
        "path": str(resolved),
        "opened_at": datetime.now(timezone.utc).isoformat(),
    }
    if last_page is not None:
        row["last_page"] = str(last_page)
    if last_page_index is not None:
        row["last_page_index"] = int(last_page_index)
    rows = [row, *remaining][:30]
    save_recent_projects(rows, path)
    return rows


def remove_recent_project(root: Path, path: Path | None = None) -> list[dict[str, object]]:
    """Remove only the registry row. No project path is ever unlinked."""
    resolved = root.expanduser().resolve()
    rows = [row for row in load_recent_projects(path) if Path(str(row["path"])).expanduser() != resolved]
    save_recent_projects(rows, path)
    return rows


def _display_recent_timestamp(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return text[:16] if len(text) >= 16 else text


def recent_project_details(row: dict[str, object]) -> dict[str, str | int | bool]:
    """Read display metadata without initializing or modifying the project."""
    root = Path(str(row.get("path") or "")).expanduser()
    last_page = str(row.get("last_page") or "").strip()
    try:
        last_page_index = int(row.get("last_page_index")) if row.get("last_page_index") is not None else -1
    except (TypeError, ValueError):
        last_page_index = -1
    details: dict[str, str | int | bool] = {
        "full_name": str(row.get("name") or root.name),
        "abbreviation": "",
        "image_count": 0,
        "last_edited": _display_recent_timestamp(row.get("opened_at")),
        "path": str(root),
        "exists": root.is_dir(),
        "last_page": last_page,
        "last_page_index": last_page_index,
        "resume_text": last_page or "—",
        "position_text": "—",
        "cover_path": "",
        "preview_path": "",
        "cover_source": "none",
    }
    if not root.is_dir():
        return details
    try:
        pages = project_page_images(root)
        details["image_count"] = len(pages)
        cover = project_cover_path(root)
        if cover is not None:
            details["cover_path"] = str(cover)
            details["preview_path"] = str(cover)
            details["cover_source"] = "cover"
        elif pages:
            details["preview_path"] = str(pages[0])
            details["cover_source"] = "first_page"
        image_count = int(details["image_count"])
        if last_page_index >= 0 and image_count > 0:
            page_number = min(image_count, last_page_index + 1)
            details["position_text"] = f"第 {page_number:,} / {image_count:,} 页"
        elif last_page:
            details["position_text"] = last_page
    except OSError:
        details["exists"] = False
        return details
    project_settings = settings_path(root)
    if project_settings.is_file():
        try:
            raw = json.loads(project_settings.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                details["full_name"] = str(raw.get("dictionary_full_name") or details["full_name"])
                details["abbreviation"] = str(raw.get("dictionary_abbreviation") or "")
        except (OSError, ValueError, TypeError):
            pass
    try:
        candidates = [root.stat().st_mtime]
    except OSError:
        return details
    metadata = project_settings.parent
    if metadata.is_dir():
        try:
            candidates.extend(item.stat().st_mtime for item in metadata.iterdir() if item.is_file())
        except OSError:
            pass
    details["last_edited"] = datetime.fromtimestamp(max(candidates)).strftime("%Y-%m-%d %H:%M")
    return details
