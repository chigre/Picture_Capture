"""Persistent, project-local, source-validated thumbnails for the page index.

This is a disposable, derived cache, never the original scan or annotation.
Each PNG contains its own source fingerprint, so a crash between writes cannot
make a stale thumbnail appear valid. Cache publication uses os.replace.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

from PIL import Image, ImageOps, PngImagePlugin

from picture_capture.project_storage import storage_root

CACHE_VERSION = "page-index-v1"
CACHE_BOUNDS = (160, 224)
FINGERPRINT_KEY = "picture_capture_source_fingerprint"


def thumbnail_cache_dir(project_root: Path) -> Path:
    return storage_root(project_root) / "cache" / "page_index_thumbnails"


def thumbnail_cache_path(project_root: Path, source_path: Path) -> Path:
    canonical = str(Path(source_path).resolve())
    stem = hashlib.sha256(canonical.encode("utf-8", "surrogatepass")).hexdigest()
    return thumbnail_cache_dir(project_root) / stem[:2] / (stem + ".png")


def source_fingerprint(source_path: Path) -> str:
    """Detect source replacement and edits without decoding every full scan."""
    path = Path(source_path).resolve()
    stat = path.stat()
    signature = [
        CACHE_VERSION, str(path), int(stat.st_dev), int(stat.st_ino),
        int(stat.st_size), int(stat.st_mtime_ns), int(stat.st_ctime_ns),
    ]
    payload = json.dumps(signature, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8", "surrogatepass")).hexdigest()


def _read_valid_thumbnail(cache_path: Path, fingerprint: str) -> Image.Image | None:
    try:
        with Image.open(cache_path) as saved:
            if saved.format != "PNG" or saved.info.get(FINGERPRINT_KEY) != fingerprint:
                return None
            if not (0 < saved.width <= CACHE_BOUNDS[0] and 0 < saved.height <= CACHE_BOUNDS[1]):
                return None
            saved.load()
            return saved.convert("RGB")
    except (OSError, ValueError, SyntaxError):
        return None


def _build_thumbnail(source_path: Path) -> Image.Image:
    with Image.open(source_path) as source:
        source.draft("RGB", CACHE_BOUNDS)
        display = ImageOps.exif_transpose(source)
        display.thumbnail(CACHE_BOUNDS, Image.Resampling.LANCZOS)
        return display.convert("RGB")


def _publish_cache(image: Image.Image, destination: Path, signature: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".thumbnail-", suffix=".tmp", dir=str(destination.parent),
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            meta = PngImagePlugin.PngInfo()
            meta.add_text(FINGERPRINT_KEY, signature)
            image.save(stream, format="PNG", pnginfo=meta)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def get_page_thumbnail(project_root: Path, source_path: Path) -> Image.Image:
    """Return a displayable preview even when the cache is read-only/unwritable.

    The cache is purely optional. A corrupt, stale or absent file regenerates
    from the original image. No source image or user-owned file is changed.
    """
    signature = source_fingerprint(source_path)
    destination = thumbnail_cache_path(project_root, source_path)
    image = _read_valid_thumbnail(destination, signature)
    if image is not None:
        return image
    image = _build_thumbnail(source_path)
    # A scan replaced while decoding cannot publish an incorrectly labelled PNG.
    if source_fingerprint(source_path) != signature:
        raise OSError("Source scan changed during thumbnail decode")
    try:
        _publish_cache(image, destination, signature)
    except OSError:
        # Read-only project: keep previews visible without modifying originals.
        pass
    return image


def display_page_thumbnail(project_root: Path, source_path: Path, width: int) -> Image.Image:
    image = get_page_thumbnail(project_root, source_path)
    image.thumbnail((int(width), round(int(width) * 1.4)), Image.Resampling.LANCZOS)
    return image
