"""User-level recent-project registry (never deletes project data)."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time

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
                rows = [row for row in value if isinstance(row, dict) and row.get("path")]
                return sorted(rows, key=lambda row: not bool(row.get("pinned", False)))
        except (OSError, ValueError, TypeError):
            continue
    return []


def save_recent_projects(rows: list[dict[str, object]], path: Path | None = None) -> None:
    target = path or default_recent_projects_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp = Path(handle.name)
            json.dump(rows, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(5):
            try:
                os.replace(temp, target)
                break
            except PermissionError:
                # On Windows, competing writers can briefly lock the destination
                # during replacement. Never retry other I/O errors indefinitely.
                if attempt == 4:
                    raise
                time.sleep(0.025 * (attempt + 1))
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


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


def set_recent_project_pinned(
    root: Path, pinned: bool, path: Path | None = None,
) -> list[dict[str, object]]:
    """Keep pinned projects above other recent entries without deleting data."""
    resolved = Path(root).expanduser().resolve()
    rows = load_recent_projects(path)
    for row in rows:
        if Path(str(row.get("path", ""))).expanduser() == resolved:
            row["pinned"] = bool(pinned)
    rows.sort(key=lambda row: not bool(row.get("pinned", False)))
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


def recent_project_stub_details(row: dict[str, object]) -> dict[str, str | int | bool]:
    """Render an immediate card from the user registry, without touching disk."""
    root = Path(str(row.get("path") or "")).expanduser()
    last_page = str(row.get("last_page") or "").strip()
    try:
        index = int(row.get("last_page_index")) if row.get("last_page_index") is not None else -1
    except (TypeError, ValueError, OverflowError):
        index = -1
    cached = row.get("card_cache")
    if isinstance(cached, dict) and cached.get("version") == 1:
        detail = {
            key: cached[key] for key in (
                "full_name", "abbreviation", "image_count", "last_edited",
                "cover_path", "preview_path", "cover_source",
            ) if key in cached
        }
    else:
        detail = {}
    result = {
        **detail,
        "full_name": str(detail.get("full_name") or row.get("name") or root.name),
        "abbreviation": str(detail.get("abbreviation") or ""),
        "image_count": int(detail.get("image_count") or 0),
        "last_edited": str(detail.get("last_edited") or _display_recent_timestamp(row.get("opened_at"))),
        "path": str(root),
        "exists": True,  # Unknown until filesystem metadata is loaded.
        "checking": True,
        "last_page": last_page,
        "last_page_index": index,
        "resume_text": last_page or "—",
        "position_text": last_page or "—",
        "cover_path": str(detail.get("cover_path") or ""),
        "preview_path": str(detail.get("preview_path") or ""),
        "cover_source": str(detail.get("cover_source") or "none"),
    }
    count = int(result["image_count"])
    if count and index >= 0:
        result["position_text"] = f"第 {min(count, index + 1):,} / {count:,} 页"
    result["checking"] = not bool(detail)
    return result


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
    if not details["exists"]:
        return details
    # Match the same selected image format used by ProjectState on opening.
    # Counting every supported image in mixed TIFF/PNG/JPG directories gives
    # misleading page totals and incorrect resume-page denominators.
    project_settings = settings_path(root)
    raw: dict[str, object] = {}
    if project_settings.is_file():
        try:
            loaded = json.loads(project_settings.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                raw = loaded
        except (OSError, ValueError, TypeError):
            pass
    details["full_name"] = str(raw.get("dictionary_full_name") or details["full_name"])
    details["abbreviation"] = str(raw.get("dictionary_abbreviation") or "")
    preferred_suffix = str(raw.get("image_suffix") or "").lower().strip()
    if preferred_suffix and not preferred_suffix.startswith("."):
        preferred_suffix = "." + preferred_suffix
    try:
        inventory = tuple(root.iterdir())
        all_pages = project_page_images(root, candidates=inventory)
        if all_pages:
            chosen_suffix = preferred_suffix if any(
                page.suffix.lower() == preferred_suffix for page in all_pages
            ) else all_pages[0].suffix.lower()
            pages = [page for page in all_pages if page.suffix.lower() == chosen_suffix]
        else:
            pages = []
        details["image_count"] = len(pages)
        cover = project_cover_path(root, candidates=inventory)
        if cover is not None:
            details["cover_path"] = str(cover)
            details["preview_path"] = str(cover)
            details["cover_source"] = "cover"
        elif pages:
            details["preview_path"] = str(pages[0])
            details["cover_source"] = "first_page"
        image_count = len(pages)
        if last_page_index >= 0 and image_count > 0:
            page_number = min(image_count, last_page_index + 1)
            details["position_text"] = f"第 {page_number:,} / {image_count:,} 页"
        elif last_page:
            details["position_text"] = last_page
    except OSError:
        details["exists"] = False
        return details
    try:
        candidates = [root.stat().st_mtime]
    except OSError:
        return details
    metadata = project_settings.parent
    if metadata == root:
        # Legacy projects store scans beside settings. Iterating/stat-ing every
        # high-volume scan to compute a card timestamp is unnecessarily slow.
        try:
            if project_settings.is_file():
                candidates.append(project_settings.stat().st_mtime)
        except OSError:
            pass
    elif metadata.is_dir():
        try:
            candidates.extend(item.stat().st_mtime for item in metadata.iterdir() if item.is_file())
        except OSError:
            pass
    details["last_edited"] = datetime.fromtimestamp(max(candidates)).strftime("%Y-%m-%d %H:%M")
    return details
