from __future__ import annotations

"""Export physical Layout rows that do not have a current PDIC marker.

The authoritative row universe is Layout Core: ``column.lines`` contains every
recovered physical text row.  PDIC is the authoritative set of lines the user
actually has drawn.  This module deliberately computes ``Layout rows - PDIC
matched rows`` rather than treating ``role == body`` as synonymous with
"unlined"; role classification can be wrong while the visible marker state is
still unambiguous.

The exported crop is the leftmost selected percentage of each column using
the project's visible “向右比例” setting. Near-blank detection applies to this
small prefix rather than to the entire physical text row, allowing users to
find candidate lines lacking headwords/entry markers.

Optional export filters are evaluated on the original Layout row crop before any
white-border trimming.  That ordering is essential for the ``blank`` filter: a
nearly empty full-width row must not become a tiny high-density speck crop before
its blankness is measured.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from multiprocessing import get_context
from pathlib import Path
import os
from typing import Any, Callable

import numpy as np
from PIL import Image

from . import dictionary_page_design as page_design
from . import formats
from .image_utils import build_analysis_image, normalize_page_rgb
from .layout_core_understanding import understand_layout_core
from .page_sections import read_page_sections, section_index_for_v, v_is_inside_sections
from .project_storage import qt_root
from .single_line_merge_settings import _trim_white_border, load_merge_by_page
from .single_line_parallel import configured_single_line_workers
from .unlined_export_filter_settings import (
    DEFAULT_BLANK_INK_PERCENT,
    load_unlined_filter_settings,
)
from .unlined_physical_rows_resolver import resolve_unlined_physical_rows


OUTPUT_DIRNAME = "PSW_UNLINED"
MANIFEST_SUFFIX = ".UnlinedLines"


@dataclass(frozen=True, slots=True)
class UnlinedRow:
    column_index: int
    line_index: int
    role: str
    source_box: tuple[int, int, int, int]
    section_index: int


@dataclass(frozen=True, slots=True)
class UnlinedPageResult:
    page_index: int
    filename: str
    layout_rows: int
    lined_rows: int
    unlined_rows: int
    exported_images: int
    blank_rows: int
    filtered_out_rows: int
    merged: bool
    physical_reliable: bool


def _column_for_canonical_x(layout: Any, x: int) -> Any | None:
    columns = list(getattr(layout, "columns", []) or [])
    if not columns:
        return None
    containing = [
        column
        for column in columns
        if int(getattr(column, "left", 0)) - 2 <= int(x) <= int(getattr(column, "right", 0)) + 2
    ]
    return min(
        containing or columns,
        key=lambda column: abs(int(x) - int(getattr(column, "left", 0))),
    )


def _line_boundary_local(column: Any, line: Any, reference: float) -> int:
    return int(page_design._boundary_before(
        list(getattr(column, "lines", []) or []),
        int(getattr(line, "y0", 0)),
        max(1.0, float(reference)),
    ))


def matched_lined_row_keys(layout: Any, entries: list[Any]) -> set[tuple[int, int]]:
    """Map every current PDIC marker to its nearest Layout row in that column.

    A drawn marker is a boundary *before* a row, not the row's ink top. Matching
    therefore uses the same ``_boundary_before`` model that Layout uses to place
    entry boundaries. We intentionally do not inspect ``line.role`` here.
    """
    columns = list(getattr(layout, "columns", []) or [])
    if not columns:
        return set()
    source_size = tuple(getattr(layout, "source_size", (0, 0)) or (0, 0))
    body_top = int(getattr(layout, "body_top", 0) or 0)
    body_bottom = int(getattr(layout, "body_bottom", body_top + 1) or (body_top + 1))
    reference = max(1.0, float(getattr(layout, "ordinary_line_height", 1.0) or 1.0))
    result: set[tuple[int, int]] = set()

    for entry in entries:
        try:
            u, v = layout.transform.source_to_canonical_point(
                int(entry.x), int(entry.y), source_size,
            )
        except Exception:
            continue
        if int(v) < body_top - round(reference) or int(v) > body_bottom + round(reference):
            continue
        column = _column_for_canonical_x(layout, int(u))
        if column is None:
            continue
        lines = list(getattr(column, "lines", []) or [])
        if not lines:
            continue
        local_v = float(int(v) - body_top)
        nearest_index = min(
            range(len(lines)),
            key=lambda index: abs(
                local_v - _line_boundary_local(column, lines[index], reference)
            ),
        )
        result.add((int(getattr(column, "index", 0)), int(nearest_index)))
    return result


def _source_box_for_line(layout: Any, column: Any, line: Any, *, right_ratio: float = 100.0) -> tuple[int, int, int, int]:
    """Convert one canonical Layout row rectangle back to a source-image box."""
    source_width, source_height = tuple(getattr(layout, "source_size", (0, 0)) or (0, 0))
    if source_width <= 0 or source_height <= 0:
        raise ValueError("Layout source size is invalid")
    body_top = int(getattr(layout, "body_top", 0) or 0)
    reference = max(1.0, float(getattr(layout, "ordinary_line_height", 1.0) or 1.0))
    pad_y = max(1, round(reference * 0.05))
    x0 = int(getattr(column, "left", 0))
    column_right = int(getattr(column, "right", x0 + 1))
    try:
        ratio = float(right_ratio)
    except (TypeError, ValueError, OverflowError):
        ratio = 100.0
    if not np.isfinite(ratio):
        ratio = 100.0
    # The exported diagnostic is the column's left prefix, not the whole row.
    # Transform the canonical prefix corners into source coordinates so rotated
    # or flipped pages use the same logical left edge.
    ratio = max(1.0, min(100.0, ratio)) / 100.0
    x1 = max(x0 + 1, min(column_right, x0 + round((column_right - x0) * ratio)))
    y0 = body_top + int(getattr(line, "y0", 0)) - pad_y
    y1 = body_top + int(getattr(line, "y1", 0)) + pad_y

    corners = [
        layout.transform.canonical_to_source_point(x0, y0, layout.source_size),
        layout.transform.canonical_to_source_point(x1, y0, layout.source_size),
        layout.transform.canonical_to_source_point(x0, y1, layout.source_size),
        layout.transform.canonical_to_source_point(x1, y1, layout.source_size),
    ]
    xs = [int(point[0]) for point in corners]
    ys = [int(point[1]) for point in corners]
    left = max(0, min(source_width - 1, min(xs)))
    right = max(left + 1, min(source_width, max(xs)))
    top = max(0, min(source_height - 1, min(ys)))
    bottom = max(top + 1, min(source_height, max(ys)))
    return left, top, right, bottom


def unlined_rows_from_layout(
    layout: Any,
    entries: list[Any],
    page_sections: list[Any] | None,
    *,
    right_ratio: float = 100.0,
) -> tuple[list[UnlinedRow], int, int]:
    """Return physical rows with no matched PDIC marker in reading order."""
    lined = matched_lined_row_keys(layout, entries)
    body_top = int(getattr(layout, "body_top", 0) or 0)
    body_bottom = int(getattr(layout, "body_bottom", body_top + 1) or (body_top + 1))
    rows: list[UnlinedRow] = []
    eligible_keys: set[tuple[int, int]] = set()

    for column in list(getattr(layout, "columns", []) or []):
        column_index = int(getattr(column, "index", 0))
        for line_index, line in enumerate(list(getattr(column, "lines", []) or [])):
            center_v = body_top + round(
                (int(getattr(line, "y0", 0)) + int(getattr(line, "y1", 0))) / 2.0
            )
            if not v_is_inside_sections(center_v, page_sections, body_top, body_bottom):
                continue
            key = (column_index, int(line_index))
            eligible_keys.add(key)
            if key in lined:
                continue
            rows.append(UnlinedRow(
                column_index=column_index,
                line_index=int(line_index),
                role=str(getattr(line, "role", "unknown") or "unknown"),
                source_box=_source_box_for_line(layout, column, line, right_ratio=right_ratio),
                section_index=section_index_for_v(
                    center_v, page_sections, body_top, body_bottom,
                ),
            ))

    # line_index follows canonical top-to-bottom order inside each column. Do
    # not sort by source Y because rotated/flipped Layout transforms can make
    # source-space Y differ from logical reading order.
    rows.sort(key=lambda row: (row.section_index, row.column_index, row.line_index))
    return rows, len(eligible_keys), len(lined & eligible_keys)


def row_ink_percent(image: Image.Image) -> float:
    """Return effective foreground-ink percentage for one original row crop.

    The paper background is estimated from the bright tail of the crop itself,
    so yellow/aged paper is not mistaken for text merely because it is darker
    than pure white. Pixels at least about 18 gray levels below that local
    background (capped at 235) count as ink. The result must be computed before
    any content-tight trimming.
    """
    gray_image = image.convert("L")
    try:
        gray = np.asarray(gray_image, dtype=np.uint8)
    finally:
        gray_image.close()
    if gray.size == 0:
        return 0.0
    background = float(np.percentile(gray, 90.0))
    cutoff = int(max(0.0, min(235.0, background - 18.0)))
    ink = gray <= cutoff
    return float(ink.mean() * 100.0)


def is_near_blank_row(
    image: Image.Image,
    max_ink_percent: float = DEFAULT_BLANK_INK_PERCENT,
) -> bool:
    try:
        limit = max(0.0, float(max_ink_percent))
    except (TypeError, ValueError):
        limit = DEFAULT_BLANK_INK_PERCENT
    return row_ink_percent(image) <= limit


def _atomic_text(path: Path, text: str) -> None:
    temp = path.with_name(f".{path.name}.tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def _save_unlined_rows(
    source: Image.Image,
    image_path: Path,
    rows: list[UnlinedRow],
    output_dir: Path,
    *,
    merge_by_page: bool,
    filter_enabled: bool,
    filter_blank: bool,
    blank_ink_percent: float,
) -> tuple[int, int, int, bool]:
    """Filter then save unlined rows, optionally merging one page vertically.

    Blank filtering uses the untrimmed Layout crop. When that filter is active,
    retained images intentionally preserve their original row frame so users can
    visually see that the row is nearly empty. Without the blank filter, normal
    content rows are white-trimmed for compact output, while a genuinely all-white
    row is retained rather than silently discarded because this exporter is a
    diagnostic surface.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = image_path.stem
    manifest = output_dir / f"{stem}{MANIFEST_SUFFIX}"
    stale = list(output_dir.glob(f"{stem}_UL_*.png"))
    images: list[Image.Image] = []
    blank_rows = 0
    filtered_out = 0
    blank_filter_active = bool(filter_enabled and filter_blank)

    try:
        for row in rows:
            crop = source.crop(row.source_box)
            try:
                ink_percent = row_ink_percent(crop)
                near_blank = ink_percent <= max(0.0, float(blank_ink_percent))
                if near_blank:
                    blank_rows += 1
                if blank_filter_active and not near_blank:
                    filtered_out += 1
                    continue

                if blank_filter_active:
                    # Preserve the whole row frame: trimming a near-blank slice
                    # down to one dust speck would destroy the visual evidence
                    # that it was almost entirely blank.
                    images.append(crop.convert("RGB"))
                    continue

                trimmed = _trim_white_border(crop)
                if trimmed is None:
                    # Unlike ordinary single-line merge, blank rows are meaningful
                    # diagnostics here and must survive the unfiltered export.
                    images.append(crop.convert("RGB"))
                else:
                    images.append(trimmed)
            finally:
                crop.close()

        if not images:
            _atomic_text(manifest, "")
            for path in stale:
                path.unlink(missing_ok=True)
            return 0, blank_rows, filtered_out, False

        replacements: list[tuple[Path, Path]] = []
        names: list[str] = []
        merged = False
        if merge_by_page:
            name = f"{stem}_UL_PAGE.png"
            target = output_dir / name
            temp = output_dir / f".{name}.tmp"
            width = max(image.width for image in images)
            height = sum(image.height for image in images)
            canvas = Image.new("RGB", (max(1, width), max(1, height)), "white")
            try:
                y = 0
                for image in images:
                    canvas.paste(image, (0, y))
                    y += image.height
                canvas.save(temp, format="PNG")
            finally:
                canvas.close()
            replacements.append((temp, target))
            names.append(name)
            merged = True
        else:
            for index, image in enumerate(images):
                name = f"{stem}_UL_{index:03d}.png"
                target = output_dir / name
                temp = output_dir / f".{name}.tmp"
                image.save(temp, format="PNG")
                replacements.append((temp, target))
                names.append(name)

        manifest_temp = output_dir / f".{manifest.name}.tmp"
        manifest_temp.write_text("\n".join(names) + "\n", encoding="utf-8")
        try:
            for temp, target in replacements:
                os.replace(temp, target)
            os.replace(manifest_temp, manifest)
        except Exception:
            manifest_temp.unlink(missing_ok=True)
            for temp, _target in replacements:
                temp.unlink(missing_ok=True)
            raise

        keep = {target.resolve() for _temp, target in replacements}
        for path in stale:
            if path.resolve() not in keep:
                path.unlink(missing_ok=True)
        return len(images) if not merged else 1, blank_rows, filtered_out, merged
    finally:
        for image in images:
            image.close()


def export_unlined_page_job(
    project_root: str | Path,
    image_path: str | Path,
    page_index: int,
    settings: Any,
    merge_by_page: bool,
    filter_enabled: bool,
    filter_blank: bool,
    blank_ink_percent: float,
) -> UnlinedPageResult:
    """Spawn-safe one-page exporter using physical-row-only recovery."""
    project_root = Path(project_root)
    image_path = Path(image_path)
    output_dir = qt_root(project_root) / OUTPUT_DIRNAME
    entries = formats.read_pdic(formats.pdic_path(image_path))
    sections = read_page_sections(image_path)

    with Image.open(image_path) as opened:
        source = normalize_page_rgb(opened)
    try:
        layout, _resolved_source = resolve_unlined_physical_rows(
            project_root,
            image_path,
            source,
            settings,
            page_index=int(page_index),
        )
        if layout is None:
            return UnlinedPageResult(
                int(page_index), image_path.name, 0, 0, 0, 0, 0, 0, False, False
            )
        rows, layout_rows, lined_rows = unlined_rows_from_layout(
            layout,
            entries,
            sections,
            right_ratio=getattr(settings, "right_ratio", 100.0),
        )
        exported, blanks, filtered_out, merged = _save_unlined_rows(
            source,
            image_path,
            rows,
            output_dir,
            merge_by_page=bool(merge_by_page),
            filter_enabled=bool(filter_enabled),
            filter_blank=bool(filter_blank),
            blank_ink_percent=float(blank_ink_percent),
        )
        return UnlinedPageResult(
            int(page_index),
            image_path.name,
            int(layout_rows),
            int(lined_rows),
            len(rows),
            int(exported),
            int(blanks),
            int(filtered_out),
            bool(merged),
            True,
        )
    finally:
        source.close()


def run_unlined_export(
    project_root: Path,
    images: tuple[Path, ...],
    indices: tuple[int, ...],
    settings: Any,
    progress: Callable[[int, int, UnlinedPageResult, int], None],
) -> tuple[int, int, int, int, Path, bool, int]:
    """Export selected pages using the existing crop worker-count setting."""
    project_root = Path(project_root)
    output_dir = qt_root(project_root) / OUTPUT_DIRNAME
    output_dir.mkdir(parents=True, exist_ok=True)
    merge_by_page = load_merge_by_page(project_root)
    filter_enabled, filter_blank, blank_ink_percent = load_unlined_filter_settings(
        project_root
    )
    total = len(indices)
    workers = max(1, min(configured_single_line_workers(project_root), max(1, total)))
    completed = 0
    total_unlined = 0
    total_exported = 0
    unreliable = 0

    def consume(result: UnlinedPageResult) -> None:
        nonlocal completed, total_unlined, total_exported, unreliable
        completed += 1
        total_unlined += int(result.unlined_rows)
        total_exported += int(result.exported_images)
        if not result.physical_reliable:
            unreliable += 1
        progress(completed, total, result, workers)

    job_args = (
        bool(merge_by_page),
        bool(filter_enabled),
        bool(filter_blank),
        float(blank_ink_percent),
    )

    if workers <= 1:
        for index in indices:
            consume(export_unlined_page_job(
                project_root, images[index], index, settings, *job_args
            ))
        return total, total_unlined, total_exported, unreliable, output_dir, merge_by_page, 1

    context = get_context("spawn")
    executor = ProcessPoolExecutor(max_workers=workers, mp_context=context)
    futures = []
    try:
        for index in indices:
            futures.append(executor.submit(
                export_unlined_page_job,
                str(project_root),
                str(images[index]),
                int(index),
                settings,
                *job_args,
            ))
        for future in as_completed(futures):
            consume(future.result())
    except Exception:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)

    return total, total_unlined, total_exported, unreliable, output_dir, merge_by_page, workers


__all__ = [
    "MANIFEST_SUFFIX",
    "OUTPUT_DIRNAME",
    "UnlinedPageResult",
    "UnlinedRow",
    "export_unlined_page_job",
    "is_near_blank_row",
    "matched_lined_row_keys",
    "row_ink_percent",
    "run_unlined_export",
    "unlined_rows_from_layout",
]
