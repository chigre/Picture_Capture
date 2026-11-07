"""Spawn-safe WW and PPP crop worker algorithms.

Callers preserve the old multiprocessing import paths in processing_core.
Page loaders, publishers and previous-entry relation hooks stay patchable.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from pathlib import Path
    from ..models import AppSettings
    from ..processing_core import CropRecord, IllustrationSplitResult


def split_whole_entries_job_impl(
    image_path: str | Path,
    pdic_file: str | Path,
    settings: AppSettings,
    output_dir: str | Path,
    top_y: int | None = None,
    bottom_y: int | None = None,
    ppp_file: str | Path | None = None,
    entry_left_padding: int = 0,
    entry_right_padding: int = 0,
    integrate_illustrations: bool = True,
    profile_page_index: int = 0,
    transparent_background: bool = False,
    previous_image_path: str | Path | None = None,
    *, deps: dict[str, Any],
) -> list[CropRecord]:
    """Spawn-safe worker: build the crop plan first, then execute it."""
    Path = deps["Path"]
    read_pdic = deps["read_pdic"]
    read_ppp = deps["read_ppp"]
    split_whole_entries = deps["split_whole_entries"]
    previous_entry_ref_for_image = deps["previous_entry_ref_for_image"]
    page = Path(image_path)
    entries = read_pdic(Path(pdic_file))
    polygons = read_ppp(Path(ppp_file)) if ppp_file else []
    return split_whole_entries(
        page, entries, settings, Path(output_dir), top_y=top_y, bottom_y=bottom_y, polygons=polygons,
        entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
        integrate_illustrations=integrate_illustrations,
        profile_page_index=profile_page_index,
        transparent_background=transparent_background,
        previous_entry_ref=previous_entry_ref_for_image(previous_image_path),
    )


def split_illustrations_job_impl(
    image_path: str | Path,
    ppp_file: str | Path,
    output_dir: str | Path,
    settings: AppSettings | None = None,
    top_y: int = 0,
    bottom_y: int = 0,
    margin: int = 0,
    pdic_file: str | Path | None = None,
    entry_left_padding: int = 0,
    entry_right_padding: int = 0,
    integrate_illustrations: bool = True,
    profile_page_index: int = 0,
    transparent_background: bool = False,
    previous_image_path: str | Path | None = None,
    *, deps: dict[str, Any],
) -> IllustrationSplitResult:
    """Spawn-safe worker: plan PPP/entry relations before exporting standalone PPPs."""
    Path = deps["Path"]
    read_ppp = deps["read_ppp"]
    read_pdic = deps["read_pdic"]
    split_illustrations = deps["split_illustrations"]
    previous_entry_ref_for_image = deps["previous_entry_ref_for_image"]
    page = Path(image_path)
    polygons = read_ppp(Path(ppp_file))
    entries = read_pdic(Path(pdic_file)) if pdic_file else []
    return split_illustrations(
        page, polygons, Path(output_dir), settings, top_y=top_y, bottom_y=bottom_y, margin=margin, entries=entries,
        entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
        integrate_illustrations=integrate_illustrations,
        profile_page_index=profile_page_index,
        transparent_background=transparent_background,
        previous_entry_ref=previous_entry_ref_for_image(previous_image_path),
    )
