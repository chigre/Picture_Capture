from __future__ import annotations

"""PNG-only output formatting; never changes source-space crop coordinates."""

import os
from pathlib import Path
from uuid import uuid4

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


def _pad_png(path: Path, target_width: int, *, transparent: bool) -> bool:
    with Image.open(path) as source:
        if source.width >= target_width:
            return False
        mode = "RGBA" if transparent else "RGB"
        fill = (0, 0, 0, 0) if transparent else "white"
        canvas = Image.new(mode, (target_width, source.height), fill)
        original = (
            prepare_crop_background(source, transparent=False)
            if mode == "RGB" and source.mode in {"RGBA", "LA", "P"}
            else source.convert(mode)
        )
        canvas.paste(original, (0, 0))
        original.close()
    # Atomic replacement: a stopped operation never leaves a truncated PNG.
    temp = path.with_name(f".{path.stem}.{uuid4().hex}.tmp.png")
    try:
        canvas.save(temp, format="PNG")
        os.replace(temp, path)
    finally:
        canvas.close()
        temp.unlink(missing_ok=True)
    return True


def normalize_project_crop_widths(project_root: Path, config: dict) -> dict[str, int]:
    """Pad exported PWW/PIC PNGs to the same *entry* target, without rescaling.

    Called only after parallel per-page exporters complete, so no worker can
    observe a moving global maximum. Auto mode examines the entire project's
    existing PWW outputs, rather than just the selected pages. Previously
    padded widths remain stable for subsequent partial re-exports.
    """
    mode = str(config.get(ENTRY_WIDTH_MODE_KEY, "auto"))
    if mode not in {"off", "auto", "fixed"}:
        raise ValueError(f"Invalid entry width mode: {mode}")
    stats = {"target_width": 0, "entries_padded": 0, "illustrations_padded": 0, "oversize": 0}
    if mode == "off":
        return stats

    root = qt_root(Path(project_root))
    entries = sorted((root / "PWW").glob("*_WW_*.png"))
    if mode == "fixed":
        target = int(config.get(ENTRY_FIXED_WIDTH_KEY, 0))
        if target < 1:
            raise ValueError("手动指定的词条宽度必须大于 0")
    else:
        # PIL reads PNG size from the header; pixels are not decoded here.
        widths = []
        for path in entries:
            with Image.open(path) as item:
                widths.append(item.width)
        target = max(widths, default=0)
        if not target:
            # An illustration-only project cannot infer a word width.
            return stats

    stats["target_width"] = target
    entry_transparent = bool(config.get(ENTRY_TRANSPARENT_KEY, False))
    for path in entries:
        if _pad_png(path, target, transparent=entry_transparent):
            stats["entries_padded"] += 1
        else:
            with Image.open(path) as item:
                if item.width > target:
                    stats["oversize"] += 1

    if bool(config.get(ILLUSTRATION_PAD_WIDTH_KEY, True)):
        pictures = sorted([
            *(root / "PIC").glob("*_PIC_*.png"),
            *(root / "PIC").glob("*_WW_*.png"),
        ])
        illustration_transparent = bool(config.get(ILLUSTRATION_TRANSPARENT_KEY, False))
        for path in pictures:
            if _pad_png(path, target, transparent=illustration_transparent):
                stats["illustrations_padded"] += 1
            else:
                with Image.open(path) as item:
                    if item.width > target:
                        stats["oversize"] += 1
    return stats
