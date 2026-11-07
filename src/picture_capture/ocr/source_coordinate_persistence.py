"""Source-pixel OCR cache projection and exact pixel fingerprint helpers.

Pure implementation owners; the historical core supplies current dependencies.
Do not alter serialized candidate keys, raw cache hashes, or source Y precedence.
"""
from __future__ import annotations
from typing import Any, Callable


def source_only_persistence(value: Any) -> Any:
    """Strip temporary transformed-axis fields before writing cache/debug JSON."""
    if isinstance(value, list):
        return [source_only_persistence(item) for item in value]
    if isinstance(value, tuple):
        return [source_only_persistence(item) for item in value]
    if not isinstance(value, dict):
        return value

    result: dict[str, Any] = {}
    for key, item in value.items():
        name = str(key)
        if name.startswith("_") or "canonical" in name.casefold():
            continue
        if name in {"column_coordinate_space", "coordinate_spaces"}:
            continue
        result[name] = source_only_persistence(item)

    # Engine/member Y fields are page coordinates in persisted output and must
    # therefore equal their explicit source-image Y.
    if result.get("source_y") is not None and "y" in result:
        result["y"] = result["source_y"]
    for prefix in ("paddle", "tesseract", "lens"):
        source_key = f"{prefix}_source_y"
        axis_key = f"{prefix}_y"
        if result.get(source_key) is not None and axis_key in result:
            result[axis_key] = result[source_key]
        coarse_source_key = f"{prefix}_coarse_source_y"
        coarse_key = f"{prefix}_coarse_y"
        if result.get(coarse_source_key) is not None and coarse_key in result:
            result[coarse_key] = result[coarse_source_key]
        anchor_source_key = f"{prefix}_anchor_source_y"
        anchor_key = f"{prefix}_anchor_y"
        if result.get(anchor_source_key) is not None and anchor_key in result:
            result[anchor_key] = result[anchor_source_key]
    return result


def image_cache_fingerprint(image: Any, *, normalize_rgb_fn: Callable[[Any], Any], hash_module: Any) -> str:
    """Return an exact normalized-pixel hash for raw OCR cache invalidation."""
    rgb = normalize_rgb_fn(image)
    digest = hash_module.sha256()
    digest.update(f"{rgb.width}x{rgb.height}|RGB|".encode("ascii"))
    digest.update(rgb.tobytes())
    return digest.hexdigest()
