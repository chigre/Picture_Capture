"""Selected-page export of PDIC rows explicitly classified as major headwords.

Classification is read from EntryClassification sidecars, never inferred by
font size at export time. The same Layout row -> source coordinate conversion
as the unlined-row exporter handles rotated and mirrored pages.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tempfile

from PIL import Image

from .entry_classification import apply_classification_sidecar, get_entry_classification
from .formats import pdic_path, read_pdic
from .image_utils import normalize_page_rgb
from .project_storage import qt_root
from .single_line_merge_settings import _trim_white_border
from .unlined_line_export import _line_boundary_local, _source_box_for_line
from .unlined_physical_rows_resolver import resolve_unlined_physical_rows

OUTPUT_DIRNAME = "PSW_MAJOR_HEAD"


@dataclass(frozen=True)
class MajorHeadwordPageResult:
    page_index: int
    filename: str
    marked: int
    exported: int
    merged: bool
    layout_available: bool


def selected_major_row_boxes(layout, entries, right_ratio):
    """Return unique, reading-ordered source boxes for marked oversized rows."""
    columns = list(getattr(layout, "columns", ()) or ())
    if not columns:
        return []
    source_size = tuple(layout.source_size)
    body_top = int(layout.body_top)
    pitch = max(1.0, float(layout.ordinary_line_height))
    selected = set()
    boxes = []
    for entry in entries:
        if get_entry_classification(entry).entry_scale != "oversized":
            continue
        u, v = layout.transform.source_to_canonical_point(
            int(entry.x), int(entry.y), source_size,
        )
        col_index = min(
            range(len(columns)),
            key=lambda i: (
                0 if int(columns[i].left) <= u <= int(columns[i].right) else 1,
                abs(u - int(columns[i].left)),
            ),
        )
        column = columns[col_index]
        lines = list(getattr(column, "lines", ()) or ())
        if not lines:
            continue
        local_v = int(v) - body_top
        row_index = min(
            range(len(lines)),
            key=lambda i: abs(local_v - _line_boundary_local(column, lines[i], pitch)),
        )
        key = (col_index, row_index)
        if key in selected:
            continue
        # Refuse a distant nearest-row association (e.g., stale sidecar data).
        boundary = _line_boundary_local(column, lines[row_index], pitch)
        if abs(boundary - local_v) > max(12, round(pitch * 1.5)):
            continue
        selected.add(key)
        boxes.append((key, _source_box_for_line(
            layout, column, lines[row_index], right_ratio=right_ratio,
        )))
    return [box for _key, box in sorted(boxes)]


def _write_png_atomically(image: Image.Image, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="." + target.stem + ".", suffix=".png", dir=target.parent)
    os.close(fd)
    try:
        image.save(temp, format="PNG")
        os.replace(temp, target)
    finally:
        Path(temp).unlink(missing_ok=True)


def _remove_stale_page_outputs(output: Path, stem: str, keep: set[str]) -> None:
    if output.is_dir():
        for path in output.glob(f"{stem}_MH_*.png"):
            if path.name not in keep:
                path.unlink(missing_ok=True)


def export_major_headword_page_job(
    project_root: str | Path,
    image_path: str | Path,
    page_index: int,
    settings,
    merge_by_page: bool,
) -> MajorHeadwordPageResult:
    """Top-level spawn-safe worker, writes only page-unique output names."""
    root = Path(project_root)
    page = Path(image_path)
    output = qt_root(root) / OUTPUT_DIRNAME
    entries = read_pdic(pdic_path(page))
    apply_classification_sidecar(entries, pdic_path(page))
    marked = sum(get_entry_classification(entry).entry_scale == "oversized" for entry in entries)
    if not marked:
        _remove_stale_page_outputs(output, page.stem, set())
        return MajorHeadwordPageResult(int(page_index), page.name, 0, 0, False, True)
    with Image.open(page) as raw:
        source = normalize_page_rgb(raw)
    try:
        layout, _ = resolve_unlined_physical_rows(
            root, page, source, settings, page_index=int(page_index),
        )
        if layout is None:
            return MajorHeadwordPageResult(int(page_index), page.name, marked, 0, False, False)
        boxes = selected_major_row_boxes(layout, entries, getattr(settings, "right_ratio", 100))
        if not boxes:
            return MajorHeadwordPageResult(int(page_index), page.name, marked, 0, False, True)
        pieces = []
        try:
            for box in boxes:
                region = source.crop(box)
                trimmed = _trim_white_border(region)
                region.close()
                if trimmed is not None:
                    pieces.append(trimmed)
            if not pieces:
                _remove_stale_page_outputs(output, page.stem, set())
                return MajorHeadwordPageResult(int(page_index), page.name, marked, 0, False, True)
            if merge_by_page:
                width = max(piece.width for piece in pieces)
                height = sum(piece.height for piece in pieces)
                merged = Image.new("RGB", (width, height), "white")
                try:
                    offset = 0
                    for piece in pieces:
                        merged.paste(piece, (0, offset))
                        offset += piece.height
                    _write_png_atomically(merged, output / f"{page.stem}_MH_PAGE.png")
                finally:
                    merged.close()
                _remove_stale_page_outputs(output, page.stem, {f"{page.stem}_MH_PAGE.png"})
                return MajorHeadwordPageResult(int(page_index), page.name, marked, 1, True, True)
            for n, piece in enumerate(pieces, 1):
                _write_png_atomically(piece, output / f"{page.stem}_MH_{n:04d}.png")
            _remove_stale_page_outputs(
                output, page.stem,
                {f"{page.stem}_MH_{n:04d}.png" for n in range(1, len(pieces) + 1)},
            )
            return MajorHeadwordPageResult(int(page_index), page.name, marked, len(pieces), False, True)
        finally:
            for piece in pieces:
                piece.close()
    finally:
        source.close()
