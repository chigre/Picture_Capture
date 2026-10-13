from __future__ import annotations

"""PNG-only output formatting; never changes source-space crop coordinates."""

import json
import os
from pathlib import Path
from uuid import uuid4
from typing import Callable

from PIL import Image, ImageChops

from ..project_storage import qt_root


ENTRY_WIDTH_MODE_KEY = "entry_width_mode"
ENTRY_FIXED_WIDTH_KEY = "entry_fixed_width"
ILLUSTRATION_PAD_WIDTH_KEY = "illustration_pad_to_entry_width"
ENTRY_TRANSPARENT_KEY = "entry_transparent_background"
ILLUSTRATION_TRANSPARENT_KEY = "illustration_transparent_background"


def prepare_crop_background(crop: Image.Image, *, transparent: bool) -> Image.Image:
    """Optionally remove *exactly* pure-white pixels, respecting existing alpha.

    When disabled, polygon-mask transparency is composited onto solid white.
    In particular, this must not turn near-white scans into transparent pixels.
    """
    rgba = crop.convert("RGBA")
    if not transparent:
        background = Image.new("RGBA", rgba.size, "white")
        background.alpha_composite(rgba)
        rgba.close()
        result = background.convert("RGB")
        background.close()
        return result

    rgb_channels = rgba.split()[:3]
    whites = [
        channel.point(lambda v: 255 if v == 255 else 0)
        for channel in rgb_channels
    ]
    white_mask = ImageChops.multiply(
        ImageChops.multiply(whites[0], whites[1]), whites[2],
    )
    nonwhite_mask = ImageChops.invert(white_mask)
    alpha = ImageChops.multiply(rgba.getchannel("A"), nonwhite_mask)
    rgba.putalpha(alpha)
    return rgba


def _pad_png(
    path: Path, target_width: int, *, transparent: bool,
    original_width: int | None = None,
) -> bool:
    """Normalize width/alpha without mistaking previously added padding for ink."""
    with Image.open(path) as source:
        original_width = (
            min(source.width, max(1, int(original_width)))
            if original_width is not None else source.width
        )
        desired_width = max(original_width, int(target_width))
        expected_mode = "RGBA" if transparent else "RGB"
        if source.width == desired_width and source.mode == expected_mode:
            return False
        # A recorded natural width allows a previously padded file to shrink
        # safely when the desired width decreases. Never crop genuine pixels.
        source_crop = source.crop((0, 0, original_width, source.height))
        try:
            original = prepare_crop_background(source_crop, transparent=transparent)
        finally:
            source_crop.close()
        fill = (0, 0, 0, 0) if transparent else "white"
        canvas = Image.new(expected_mode, (desired_width, source.height), fill)
        try:
            canvas.paste(original, (0, 0))
        finally:
            original.close()
    temp = path.with_name(f".{path.stem}.{uuid4().hex}.tmp.png")
    try:
        canvas.save(temp, format="PNG")
        os.replace(temp, path)
    finally:
        canvas.close()
        temp.unlink(missing_ok=True)
    return True


def _natural_entry_widths(root: Path) -> dict[str, int]:
    """Read the original-width manifests committed with each whole-entry export."""
    saved: dict[str, int] = {}
    for manifest in (root / "PWW").glob("*.PWWWidths.json"):
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                for name, raw_width in payload.items():
                    width = int(raw_width)
                    if name.endswith(".png") and width > 0:
                        saved[name] = width
        except (OSError, ValueError, TypeError, OverflowError):
            # Older projects have no manifests; fall back to PNG widths.
            continue
    return saved


def normalize_project_crop_widths(
    project_root: Path, config: dict, *,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, int]:
    """Normalize PNG sizes and alpha after page publication.

    The natural-width sidecar is authoritative for exports created by current
    versions. Old projects without sidecars fall back conservatively to the
    PNG header, without discarding any potentially real pixels.
    """
    mode = str(config.get(ENTRY_WIDTH_MODE_KEY, "auto"))
    if mode not in {"off", "auto", "fixed"}:
        raise ValueError(f"Invalid entry width mode: {mode}")
    stats = {"target_width": 0, "entries_padded": 0, "illustrations_padded": 0, "oversize": 0}
    if mode == "off":
        return stats
    root = qt_root(Path(project_root))
    entries = sorted((root / "PWW").glob("*_WW_*.png"))
    original_widths = _natural_entry_widths(root)
    if mode == "fixed":
        target = int(config.get(ENTRY_FIXED_WIDTH_KEY, 0))
        if target < 1:
            raise ValueError("手动指定的词条宽度必须大于 0")
    else:
        widths = []
        for path in entries:
            if path.name in original_widths:
                widths.append(original_widths[path.name])
            else:
                with Image.open(path) as item:
                    widths.append(item.width)
        target = max(widths, default=0)
        if not target:
            return stats
    stats["target_width"] = target
    pictures = sorted([
        *(root / "PIC").glob("*_PIC_*.png"),
        *(root / "PIC").glob("*_WW_*.png"),
    ]) if bool(config.get(ILLUSTRATION_PAD_WIDTH_KEY, True)) else []
    total = len(entries) + len(pictures)
    processed = 0
    for group, paths, transparency in (
        ("entries_padded", entries, bool(config.get(ENTRY_TRANSPARENT_KEY, False))),
        ("illustrations_padded", pictures, bool(config.get(ILLUSTRATION_TRANSPARENT_KEY, False))),
    ):
        for path in paths:
            if cancelled is not None and cancelled():
                raise InterruptedError("切图宽度标准化已取消")
            source_width = original_widths.get(path.name) if group == "entries_padded" else None
            if _pad_png(path, target, transparent=transparency, original_width=source_width):
                stats[group] += 1
            if source_width is not None:
                if source_width > target:
                    stats["oversize"] += 1
            else:
                with Image.open(path) as image:
                    if image.width > target:
                        stats["oversize"] += 1
            processed += 1
            if progress is not None:
                progress(processed, total)
    return stats
