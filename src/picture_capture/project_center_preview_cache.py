"""Persistent project-center cover thumbnails with source invalidation.

Only card-sized previews live beneath the project's QT metadata folder.
A missing, stale or corrupt cache is rebuilt without touching scan files.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from PIL import Image

from .image_utils import normalize_page_rgb
from .project_storage import qt_root

_PREVIEW_VERSION = 1
_PREVIEW_SIZE = (76, 96)
_CONTENT_SIZE = (72, 92)


def _cache_files(root: Path) -> tuple[Path, Path]:
    directory = qt_root(root) / "cache"
    return directory / "project_center_preview.png", directory / "project_center_preview.json"


def _source_identity(source: Path) -> dict[str, object]:
    stat = source.stat()
    return {
        "name": source.name,
        "path": str(source.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "version": _PREVIEW_VERSION,
        "card_size": list(_PREVIEW_SIZE),
    }


def _valid_cache(image_path: Path, metadata_path: Path, identity: dict[str, object]) -> bool:
    if not image_path.is_file():
        return False
    try:
        value = json.loads(metadata_path.read_text(encoding="utf-8"))
        return value == identity
    except (OSError, ValueError, TypeError):
        return False


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staged: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", suffix=".tmp",
            dir=path.parent, delete=False,
        ) as handle:
            staged = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, path)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def _build_card(source: Path) -> Image.Image:
    with Image.open(source) as opened:
        opened.draft("RGB", _CONTENT_SIZE)
        opened.thumbnail(_CONTENT_SIZE, Image.Resampling.LANCZOS)
        scaled = normalize_page_rgb(opened)
    try:
        card = Image.new("RGB", _PREVIEW_SIZE, "#f4f6f8")
        card.paste(
            scaled,
            ((card.width - scaled.width) // 2, (card.height - scaled.height) // 2),
        )
        return card
    finally:
        scaled.close()


def load_project_center_preview(root: Path, source: Path) -> Image.Image | None:
    """Load or rebuild a thumbnail; writes are best effort for read-only projects."""
    try:
        identity = _source_identity(source)
    except OSError:
        return None
    image_path, metadata_path = _cache_files(root)
    if _valid_cache(image_path, metadata_path, identity):
        try:
            with Image.open(image_path) as cached:
                if cached.size == _PREVIEW_SIZE:
                    return cached.convert("RGB")
        except (OSError, ValueError):
            pass
    try:
        card = _build_card(source)
    except (OSError, ValueError, SyntaxError):
        return None
    try:
        import io
        stream = io.BytesIO()
        card.save(stream, format="PNG")
        _atomic_bytes(image_path, stream.getvalue())
        _atomic_bytes(
            metadata_path,
            json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        )
    except OSError:
        # Read-only or inaccessible project folders still show a live thumbnail.
        pass
    return card
