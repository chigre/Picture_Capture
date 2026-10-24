"""Physical owner of ordinary Entry gates and read-only OCR review observations.

Core page-template, SECTION, JSON and hard-negative dependencies are passed
at call time by the historical processing facade. No cache/sidecar writes.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from PIL import Image
from ..models import AppSettings, Entry
from ..persistence.page_sections import PageSection


def allowed_entries(
    entries: list[Entry],
    image: Image.Image,
    settings: AppSettings,
    geometry: Any,
    profile_page_index: int,
    page_sections: list[PageSection] | None,
    *,
    effective_page_settings: Any,
    entry_allowed_by_page_template: Any,
    v_is_inside_sections: Any,
) -> list[Entry]:
    # All private call sites pass detect_entries()' already-normalized source.
    # This filter only needs page size, so a second full-page RGB copy is waste.
    source_size = tuple(image.size)
    effective = effective_page_settings(
        settings, source_size, profile_page_index,
    )
    return [
        entry for entry in entries
        if entry_allowed_by_page_template(
            entry.x, entry.y, source_size, effective, profile_page_index,
        )
        and (
            not page_sections
            or v_is_inside_sections(
                geometry.source_to_canonical(entry.x, entry.y)[1],
                page_sections, geometry.top, geometry.bottom,
            )
        )
    ]


def review_candidates_from_cache(
    paddle_cache_path: Path | None,
    *,
    json_loads: Any,
) -> list[dict]:
    if paddle_cache_path is None or not paddle_cache_path.exists():
        return []
    try:
        payload = json_loads(paddle_cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(payload, dict):
        return []
    return [
        item for item in list(payload.get("review_candidates") or [])
        if isinstance(item, dict)
    ]


def hard_negative_rows_from_candidates(
    review_candidates: list[dict],
    geometry: Any,
    *,
    latent_review_rows: Any,
    hard_negative_consensus: Any,
) -> list[tuple[int, int]]:
    """Return canonical (column, V) events with OCR hard-negative consensus."""
    try:
        rows = latent_review_rows(review_candidates, geometry)
    except Exception:
        return []
    result: list[tuple[int, int]] = []
    for candidate, column, v in rows:
        try:
            hard = bool(hard_negative_consensus(candidate))
        except Exception:
            hard = False
        if hard:
            result.append((int(column), int(v)))
    return result
