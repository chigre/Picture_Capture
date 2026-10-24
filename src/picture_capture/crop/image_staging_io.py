"""Atomic source-pixel crop and manifest staging helpers.

Historical processing_core entrypoints supply the live callbacks and preserve
serializable model identity, pixel coordinates and output file contracts.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from pathlib import Path
    from PIL import Image


def save_crop_impl(
    image: Image.Image, output: Path, box: tuple[int, int, int, int],
    *, transparent_background: bool = False,
    deps: dict[str, Any],
) -> tuple[int, int, int, int]:
    clamp_box = deps["clamp_box"]
    prepare_crop_background = deps["prepare_crop_background"]
    box = clamp_box(box, image)
    output.parent.mkdir(parents=True, exist_ok=True)
    crop = image.crop(box)
    try:
        if transparent_background:
            result = prepare_crop_background(crop, transparent=True)
            try:
                result.save(output, "PNG")
            finally:
                result.close()
        else:
            crop.save(output, "PNG")
    finally:
        crop.close()
    return box


def stage_text_file_impl(target: Path, text: str, *, encoding: str = "utf-8", deps: dict[str, Any]) -> Path:
    _publish_temp_path = deps["_publish_temp_path"]
    os = deps["os"]
    temp = _publish_temp_path(target)
    try:
        with temp.open("w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        return temp
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def stage_crop_impl(
    image: Image.Image, target: Path, box: tuple[int, int, int, int],
    *, transparent_background: bool = False,
    deps: dict[str, Any],
) -> tuple[tuple[int, int, int, int], Path]:
    _publish_temp_path = deps["_publish_temp_path"]
    _save_crop = deps["_save_crop"]
    temp = _publish_temp_path(target)
    try:
        saved_box = _save_crop(image, temp, box, transparent_background=transparent_background)
        return saved_box, temp
    except Exception:
        temp.unlink(missing_ok=True)
        raise
