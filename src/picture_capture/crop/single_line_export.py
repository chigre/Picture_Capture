"""Atomic single-line word image export with manifest and stale-file cleanup.

Algorithm owner invoked by the stable processing-core facade. Runtime helpers,
models and transaction writers come from the current caller each invocation.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from ..models import AppSettings, Entry
    from ..processing_core import CropRecord
    from ..persistence.page_sections import PageSection


def split_single_lines_impl(
    image_path: Path, entries: list[Entry], settings: AppSettings, output_dir: Path,
    *, profile_page_index: int = 0, page_sections: list[PageSection] | None = None,
    write_manifest: bool = True,
    deps: dict[str, Any],
) -> list[CropRecord]:
    Image = deps["Image"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    _page_geometry_context = deps["_page_geometry_context"]
    read_page_sections = deps["read_page_sections"]
    sort_entries_reading_order = deps["sort_entries_reading_order"]
    _stage_crop = deps["_stage_crop"]
    line_box = deps["line_box"]
    CropRecord = deps["CropRecord"]
    _stage_text_file = deps["_stage_text_file"]
    _publish_file_transaction = deps["_publish_file_transaction"]
    with Image.open(image_path) as opened:
        image = normalize_page_rgb(opened)
    source, effective, _analysis_source, geometry = _page_geometry_context(
        image, settings, profile_page_index,
    )
    from ..refinement.analysis import whiten_illustrations_for_export as whiten
    source = whiten(source, effective, profile_page_index, source_image_path=image_path)
    if page_sections is None:
        page_sections = read_page_sections(image_path)
    records: list[CropRecord] = []
    manifest: list[str] = []
    replacements: list[tuple[Path, Path]] = []
    staged: list[Path] = []
    try:
        for index, entry in enumerate(sort_entries_reading_order(entries, geometry, page_sections)):
            filename = f"{image_path.stem}_SW_{index:03d}.png"
            target = output_dir / filename
            box, temp = _stage_crop(
                source, target, line_box(entry, geometry, source, effective),
            )
            staged.append(temp)
            replacements.append((temp, target))
            records.append(CropRecord(image_path.name, index, entry.word, filename, box))
            manifest.append(filename)
        manifest_target = output_dir / f"{image_path.stem}.PSWords"
        if write_manifest:
            manifest_temp = _stage_text_file(
                manifest_target, "\n".join(manifest) + ("\n" if manifest else ""),
            )
            staged.append(manifest_temp)
            replacements.append((manifest_temp, manifest_target))
        stale = list(output_dir.glob(f"{image_path.stem}_SW_*.png"))
        if not write_manifest:
            stale.append(manifest_target)
        if replacements:
            _publish_file_transaction(replacements, stale_paths=stale)
        else:
            for path in stale:
                path.unlink(missing_ok=True)
    except Exception:
        for temp in staged:
            temp.unlink(missing_ok=True)
        raise
    return records
