"""Per-page unified Layout diagnostics for the supervised training ZIP.

Use the exact read-only evidence producer behind the UI's
'导出统一Layout诊断 JSON' action, not the shorter Page Understanding summary.
The image pixels come from the already staged image in the training package.
PDIC/PPP/SECTION/Profile source data remain untouched.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

from .image_utils import normalize_page_rgb
from .page_sections import read_page_sections


def write_training_unified_layout_diagnostic(
    page: Path,
    settings: Any,
    staging_root: Path,
    page_index: int,
    image_relative: str,
) -> dict[str, Any]:
    """Write one diagnostics JSON per exported page and return its manifest ref.

    A diagnostic computation failure is explicit in the JSON and the manifest;
    it never substitutes page-design summaries or silently omits the file.
    The whole ZIP still uses the existing staged/atomic publication path.
    """
    from .large_head_visual_diagnostics import build_large_head_diagnostics

    staging_root = Path(staging_root)
    page = Path(page)
    # The copied scan, rather than a possibly changing original, is the pixel
    # authority for a reproducible training package.
    staged_image = staging_root / image_relative
    destination = (
        staging_root / "diagnostics" / "unified_layout"
        / f"{int(page_index):06d}_{page.stem}_unified_layout.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)

    image_size: list[int] | None = None
    try:
        with Image.open(staged_image) as opened:
            image = normalize_page_rgb(opened)
        try:
            image_size = [int(image.width), int(image.height)]
            snapshot = build_large_head_diagnostics(
                image, settings,
                page_index=int(page_index),
                page_sections=read_page_sections(page),
                source_image_path=page,
            )
        finally:
            image.close()
        document = {
            "schema": snapshot.get("schema", "picture-capture-ordinary-evidence-v2"),
            "page_index": int(page_index),
            "image_size": image_size,
            **snapshot,
        }
        # A result with no computed unified report is NOT a successful export.
        available = bool(
            document.get("enabled")
            and isinstance(document.get("unified_report"), dict)
        )
        if not available:
            document["available"] = False
            document["error"] = str(
                snapshot.get("message") or "Unified Layout evidence unavailable"
            )
        else:
            document["available"] = True
    except Exception as exc:
        available = False
        document = {
            "schema": "picture-capture-ordinary-evidence-v2",
            "page_index": int(page_index),
            "image_size": image_size,
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    try:
        encoded = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    except (TypeError, ValueError, OverflowError) as exc:
        # Some detector plug-ins may return non-JSON numeric objects. Never
        # advertise those diagnostics as complete or omit the page artifact.
        available = False
        document = {
            "schema": "picture-capture-ordinary-evidence-v2",
            "page_index": int(page_index),
            "image_size": image_size,
            "available": False,
            "error": f"Diagnostic JSON serialization failed: {type(exc).__name__}: {exc}",
        }
        encoded = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    destination.write_text(encoded, encoding="utf-8")
    return {
        "json": destination.relative_to(staging_root).as_posix(),
        "available": available,
        **({"error": document["error"]} if not available else {}),
    }


__all__ = ["write_training_unified_layout_diagnostic"]
