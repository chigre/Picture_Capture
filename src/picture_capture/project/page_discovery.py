"""Read-only project cover detection and natural scanned-page enumeration."""
from __future__ import annotations
from pathlib import Path
import re

def is_project_cover_image(path: Path, *, cover_stems, cover_extensions) -> bool:
    """Return True for a reserved project-card cover asset."""
    return (
        path.is_file()
        and path.stem.casefold() in {stem.casefold() for stem in cover_stems}
        and path.suffix.casefold() in cover_extensions
    )

def project_cover_path(root: Path, *, candidates: tuple[Path, ...] | None = None, cover_stems, cover_extensions) -> Path | None:
    """Find the preferred project cover without treating it as a scanned page."""
    root = Path(root)
    # _cover.* is the simple current convention. _project_cover.* remains a
    # compatibility fallback for projects that used the earlier name.
    try:
        items = candidates if candidates is not None else tuple(root.iterdir())
    except OSError:
        return None
    for stem in cover_stems:
        for suffix in cover_extensions:
            candidate = root / f"{stem}{suffix}"
            if candidate.is_file():
                return candidate
            for item in items:
                if (
                    item.is_file()
                    and item.stem.casefold() == stem.casefold()
                    and item.suffix.casefold() == suffix
                ):
                    return item
    return None

def project_page_images(root: Path, *, candidates: tuple[Path, ...] | None = None, image_extensions, is_cover_fn, natural_key_fn) -> list[Path]:
    """Return actual scanned pages, excluding the reserved project cover."""
    root = Path(root)
    try:
        pages = [
            path for path in (candidates if candidates is not None else root.iterdir())
            if (
                path.is_file()
                and path.suffix.lower() in image_extensions
                and not is_cover_fn(path)
            )
        ]
    except OSError:
        return []
    return sorted(pages, key=lambda p: natural_key_fn(p.name))

def natural_text_key(value: object) -> tuple:
    """Return the application's single natural, case-insensitive sort key."""
    parts = re.split(r"(\d+)", str(value or "").casefold())
    return tuple((0, int(part)) if part.isdigit() else (1, part) for part in parts if part)
