"""Disposable, source-validated page-index PNG cache inside the project.

One flat folder holds human-readable page names.  If two sources share a
case-insensitive stem, only those pages use a stable short path-hash suffix.
The PNG metadata binds it to the exact source path and a content-aware source
fingerprint.  Never alter source scans, OCR, PDIC, SECTION or Profiles.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from typing import Iterable, Mapping

from PIL import Image, PngImagePlugin

from picture_capture.project_storage import storage_root
from picture_capture.image_utils import normalize_page_rgb

CACHE_VERSION = "page-index-v5"
CACHE_BOUNDS = (120, 120)
FINGERPRINT_KEY = "picture_capture_source_fingerprint"
SOURCE_KEY = "picture_capture_source_path_hash"
SOURCE_FILENAME_KEY = "picture_capture_original_filename"
_SAMPLE_BYTES = 32 * 1024
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def thumbnail_cache_dir(project_root: Path) -> Path:
    return storage_root(project_root) / "cache" / "page_index_thumbnails"


def _canonical(source_path: Path) -> str:
    return str(Path(source_path).resolve())


def _path_hash(source_path: Path) -> str:
    return hashlib.sha256(_canonical(source_path).encode("utf-8", "surrogatepass")).hexdigest()


def _safe_stem(source_path: Path) -> str:
    """Keep ordinary names exactly, sanitizing only non-portable edge cases."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(source_path).stem)
    name = unicodedata.normalize("NFC", name).rstrip(" .")
    if not name:
        name = "page"
    if name.casefold() in _WINDOWS_RESERVED:
        name = "_" + name
    # Keep PNG names below Windows' per-component length even for long scans.
    if len(name.encode("utf-8")) > 180:
        name = name[:60] + "__" + _path_hash(source_path)[:12]
    return name


def thumbnail_name_map(image_paths: Iterable[Path]) -> dict[str, str]:
    """Deterministic flat filenames, safe for duplicate page names and Windows.

    E.g. 080127.jpg -> 080127.png. If both a/001.jpg and b/001.png
    exist, both are named 001__<stable-12-hex>.png.
    """
    identities = {_canonical(path): Path(path) for path in image_paths}
    stems = {identity: _safe_stem(path) for identity, path in identities.items()}
    counts = Counter(stem.casefold() for stem in stems.values())
    result = {}
    for identity, stem in stems.items():
        suffix = "__" + _path_hash(identities[identity])[:12] if counts[stem.casefold()] > 1 else ""
        result[identity] = stem + suffix + ".png"
    return result


def thumbnail_cache_path(
    project_root: Path, source_path: Path, names: Mapping[str, str] | None = None,
) -> Path:
    identity = _canonical(source_path)
    filename = names.get(identity) if names is not None else None
    return thumbnail_cache_dir(project_root) / (filename or (_safe_stem(source_path) + ".png"))


def _metadata_identity(source_path: Path) -> dict[str, str]:
    return {
        SOURCE_KEY: _path_hash(source_path),
        SOURCE_FILENAME_KEY: Path(source_path).name,
    }


def source_fingerprint(source_path: Path) -> str:
    """Metadata + sampled actual source bytes, not just a filename/stat.

    Sample beginning, quartiles, middle and end (at most ~192KiB). This detects
    ordinary in-place edits even if size/mtime are preserved, without hashing
    every huge scan on each reopen. This is a *sample*, not a full-file hash.
    """
    path = Path(source_path).resolve()
    before = path.stat()
    h = hashlib.sha256()
    identity = [
        CACHE_VERSION, str(path), int(before.st_dev), int(before.st_ino),
        int(before.st_size), int(before.st_mtime_ns), int(before.st_ctime_ns),
    ]
    h.update(json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8", "surrogatepass"))
    size = before.st_size
    starts = sorted({0, max(0, size // 4 - _SAMPLE_BYTES // 2),
                     max(0, size // 2 - _SAMPLE_BYTES // 2),
                     max(0, size * 3 // 4 - _SAMPLE_BYTES // 2),
                     max(0, size - _SAMPLE_BYTES)})
    with path.open("rb") as stream:
        for offset in starts:
            stream.seek(offset)
            block = stream.read(_SAMPLE_BYTES)
            h.update(offset.to_bytes(8, "little"))
            h.update(len(block).to_bytes(8, "little"))
            h.update(block)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns,
    ):
        raise OSError("Source image changed while computing its thumbnail fingerprint")
    return h.hexdigest()


def _read_valid_thumbnail(
    cache_path: Path, fingerprint: str, source_path: Path | None = None,
) -> Image.Image | None:
    try:
        # PNG CRC integrity check before returning cached pixel data.
        with Image.open(cache_path) as probe:
            if probe.format != "PNG" or probe.info.get(FINGERPRINT_KEY) != fingerprint:
                return None
            if source_path is not None:
                for key, value in _metadata_identity(source_path).items():
                    if probe.info.get(key) != value:
                        return None
            if not (0 < probe.width <= CACHE_BOUNDS[0] and 0 < probe.height <= CACHE_BOUNDS[1]):
                return None
            probe.verify()
        with Image.open(cache_path) as saved:
            saved.load()
            return saved.convert("RGB")
    except (OSError, ValueError, SyntaxError):
        return None


def _build_thumbnail(source_path: Path) -> Image.Image:
    """Antialias every scan mode before reducing it to a tiny full-page view.

    Pillow uses nearest-neighbor resizing for modes '1' and 'P' regardless
    of the LANCZOS argument. Converting *after* thumbnail() produced jagged
    black speckles for binary/paletted pages. Normalize EXIF, palette,
    bilevel and transparent pages to opaque RGB before resampling.
    """
    with Image.open(source_path) as source:
        source.draft("RGB", CACHE_BOUNDS)
        display = normalize_page_rgb(source)
    display.thumbnail(CACHE_BOUNDS, Image.Resampling.LANCZOS)
    return display


def _publish_cache(
    image: Image.Image, destination: Path, signature: str,
    source_path: Path | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".thumbnail-", suffix=".tmp", dir=str(destination.parent),
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            meta = PngImagePlugin.PngInfo()
            meta.add_text(FINGERPRINT_KEY, signature)
            if source_path is not None:
                for key, value in _metadata_identity(source_path).items():
                    meta.add_text(key, value)
            image.save(stream, format="PNG", pnginfo=meta)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _legacy_cache_path(project_root: Path, source_path: Path) -> Path:
    digest = _path_hash(source_path)
    return thumbnail_cache_dir(project_root) / digest[:2] / (digest + ".png")


def _retire_legacy_cache(project_root: Path, source_path: Path) -> None:
    """Remove only a specifically recognized old generated thumbnail, never unknown files."""
    old = _legacy_cache_path(project_root, source_path)
    try:
        with Image.open(old) as preview:
            if (preview.format != "PNG" or
                not isinstance(preview.info.get(FINGERPRINT_KEY), str) or
                len(preview.info[FINGERPRINT_KEY]) != 64):
                return
        old.unlink()
        old.parent.rmdir()  # Only succeeds when no other old thumbnails remain.
    except (OSError, ValueError, SyntaxError):
        pass


def get_page_thumbnail(
    project_root: Path, source_path: Path,
    names: Mapping[str, str] | None = None,
) -> Image.Image:
    """Always validate source identity, even if same-name PNG already exists."""
    signature = source_fingerprint(source_path)
    destination = thumbnail_cache_path(project_root, source_path, names)

    # The project-level name map is mandatory for ambiguous stems. A cache
    # with the right filename but another page's metadata is stale and must
    # be replaced at this exact destination, not silently diverted elsewhere.
    cached = _read_valid_thumbnail(destination, signature, source_path)
    if cached is not None:
        return cached

    # V1's old hash-directory metadata only checked path/stat, not source
    # image bytes. Never adopt an old thumbnail as proof of current pixels:
    # rebuild once from the scan, then safely retire the old disposable file.
    image = _build_thumbnail(source_path)
    # Never associate pixels decoded from an old source with a newer fingerprint.
    if source_fingerprint(source_path) != signature:
        raise OSError("Source image changed during thumbnail decode")
    try:
        _publish_cache(image, destination, signature, source_path)
    except OSError:
        # Read-only project cache: display still works from original/old preview.
        return image
    _retire_legacy_cache(project_root, source_path)
    return image


def display_page_thumbnail(
    project_root: Path, source_path: Path, width: int,
    names: Mapping[str, str] | None = None,
) -> Image.Image:
    image = get_page_thumbnail(project_root, source_path, names)
    image.thumbnail((int(width), round(int(width) * 1.4)), Image.Resampling.LANCZOS)
    return image
