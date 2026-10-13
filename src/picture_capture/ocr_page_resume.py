"""Opt-in, strictly verified per-page OCR drawing resumability.

No background jobs, no silent skips when disabled. A page can be skipped only
when its exact image content, project settings, Profile, filter rules, SECTION
structure and saved PDIC bytes still match the previous successful run.
"""
from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version as package_version
import hashlib
import json
from pathlib import Path
from typing import Any

from .formats import write_text_atomic


RESUME_FORMAT = "picture-capture-ocr-page-resume-v1"
# Increment this when changing fingerprint semantics or the source selection.
ALGORITHM_FINGERPRINT_FORMAT = "picture-capture-detection-source-tree-v2"


@lru_cache(maxsize=1)
def _algorithm_environment_key() -> str:
    """Fingerprint the *whole* detection-capable package, not a brittle shortlist.

    OCR, Layout, coordinate transforms, candidate scoring and shared Y refinement
    span many modules and are regularly extracted into new helpers. A fixed list
    silently reuses checkpoints after changes to a newly introduced module.
    Conservatively invalidating after *any* package Python source change is
    preferable to skipping a page whose drawing output might now be different.

    Source bytes and stable relative paths are hashed once per process. When
    package source is unavailable, raise OSError so validated_resume fails closed.
    """
    root = Path(__file__).resolve().parent
    sources = sorted(
        (path for path in root.rglob("*.py") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    if not sources:
        raise OSError("Cannot verify OCR resume: no readable package sources")

    digest = hashlib.sha256()
    digest.update(ALGORITHM_FINGERPRINT_FORMAT.encode("ascii"))
    for path in sources:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\\0")
        _digest_file(path, digest)

    # Detection may depend on native image/OCR distributions, not only Python
    # source. Missing optional packages have a stable sentinel, not an exception.
    for name in (
        "paddleocr", "paddlepaddle", "pytesseract", "Pillow", "numpy",
        "opencv-python", "opencv-python-headless", "chrome-lens-py",
    ):
        try:
            value = package_version(name)
        except PackageNotFoundError:
            value = "<not installed>"
        digest.update(f"{name}={value}|".encode("utf-8"))
    return digest.hexdigest()


def _digest_file(path: Path, hash_state: Any) -> None:
    path = Path(path)
    if not path.is_file():
        hash_state.update(b"no-file\0")
        return
    hash_state.update(b"present-file\0")
    with path.open("rb") as source:
        for piece in iter(lambda: source.read(1024 * 1024), b""):
            hash_state.update(piece)


def _file_hash(path: Path) -> str:
    hash_state = hashlib.sha256()
    _digest_file(path, hash_state)
    return hash_state.hexdigest()


def input_fingerprint(
    image_path: Path, settings: Any, page_index: int, method: str,
    *, dependencies: tuple[Path, ...] = (),
) -> str:
    """Strict content hash for the actual inputs (no mtime-only shortcut)."""
    digest = hashlib.sha256()
    digest.update(RESUME_FORMAT.encode("ascii"))
    digest.update(_algorithm_environment_key().encode("ascii"))
    digest.update(str(page_index).encode("ascii"))
    digest.update(str(method).encode("ascii"))
    dump = json.dumps(asdict(settings), sort_keys=True, ensure_ascii=False, default=str)
    digest.update(dump.encode("utf-8"))
    for path in (Path(image_path), *dependencies):
        digest.update(str(Path(path).name).encode("utf-8"))
        digest.update(b"\0")
        _digest_file(path, digest)
    return digest.hexdigest()


def resume_path(cache_root: Path, image_path: Path, mode: str) -> Path:
    return Path(cache_root) / "_ocr_resume" / f"{Path(image_path).stem}.{mode}.json"


def validated_resume(
    cache_root: Path, image_path: Path, pdic_path: Path,
    *, page_index: int, method: str, settings: Any,
    dependencies: tuple[Path, ...] = (),
) -> int | None:
    """Return previous final marker count only for an exact verified match."""
    path = resume_path(cache_root, image_path, method)
    if not path.exists() or not pdic_path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(raw, dict)
            or raw.get("format") != RESUME_FORMAT
            or raw.get("method") != method
            or int(raw.get("page_index", -1)) != int(page_index)
        ):
            return None
        if raw.get("pdic_sha256") != _file_hash(pdic_path):
            return None
        expected = input_fingerprint(
            image_path, settings, page_index, method, dependencies=dependencies,
        )
        if raw.get("input_sha256") != expected:
            return None
        count = int(raw.get("marker_count", -1))
        return count if count >= 0 else None
    except (ValueError, TypeError, OSError, OverflowError):
        return None


def write_page_resume(
    cache_root: Path, image_path: Path, pdic_path: Path,
    *, page_index: int, method: str, settings: Any, marker_count: int,
    dependencies: tuple[Path, ...] = (),
) -> Path:
    """Publish checkpoint ONLY AFTER PDIC was written and verified."""
    path = resume_path(cache_root, image_path, method)
    signature = input_fingerprint(
        image_path, settings, page_index, method, dependencies=dependencies,
    )
    from .formats import read_pdic
    # A truncated/invalid PDIC must never become a completed checkpoint.
    actual = read_pdic(pdic_path)
    if len(actual) != int(marker_count):
        raise ValueError("PDIC marker count changed before resume checkpoint")
    checkpoint = {
        "format": RESUME_FORMAT, "method": method,
        "page_index": int(page_index), "input_sha256": signature,
        "pdic_sha256": _file_hash(pdic_path),
        "marker_count": int(marker_count),
    }
    write_text_atomic(path, json.dumps(checkpoint, ensure_ascii=False, sort_keys=True))
    return path
