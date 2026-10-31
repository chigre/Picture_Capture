from __future__ import annotations

"""Current-page detection worker, independent of Tk lifecycle and callbacks.

The controller owns snapshotting, scheduling, page-identity checks and GUI
publication. This leaf owns source-page decoding, ordinary/OCR/combined
inference, and coordinate-safe combined text fill. Live dependencies retain
the original controller's monkeypatchable detection and OCR test seams.
"""

from pathlib import Path
from typing import Any, Mapping


def detect_current_page(
    page: Path,
    project_root: Path,
    settings: Any,
    *,
    page_index: int,
    page_sections: list[Any],
    cache_path: Path | None,
    filter_path: Path | None,
    force_paddle_refresh: bool,
    deps: Mapping[str, Any],
) -> tuple[list[Any], Any, Any]:
    """Return detected entries, geometry and optional text-fill statistics.

    In particular, never publish to the GUI or PDIC here. Those responsibilities
    stay with the parent-owned callback after it verifies the page is current.
    """
    with deps["Image"].open(page) as opened:
        image = deps["normalize_page_rgb"](opened)

    detected, geometry = deps["detect_entries"](
        image,
        settings,
        paddle_cache_path=cache_path,
        force_paddle_refresh=force_paddle_refresh,
        paddle_filter_rules_path=filter_path,
        profile_page_index=page_index,
        page_sections=page_sections,
        source_image_path=deps["detection_mask_source_path"](
            page,
            settings,
            ordinary=settings.detection_method not in {"paddleocr", "combined"},
        ),
    )
    text_stats = None
    if settings.detection_method == "combined":
        original_coords = [(int(entry.x), int(entry.y)) for entry in detected]
        detected, text_stats = deps["ocr_existing_entry_words_from_markers"](
            image,
            detected,
            settings,
            deps["load_replace_rules"](deps["replace_rules_path"](project_root)),
            profile_page_index=page_index,
            page_sections=page_sections,
            profile_path=deps["project_profile_path"](project_root),
            only_blank=True,
        )
        if [(int(entry.x), int(entry.y)) for entry in detected] != original_coords:
            raise RuntimeError("融合画线自动补字不得修改任何画线坐标")
    return detected, geometry, text_stats
