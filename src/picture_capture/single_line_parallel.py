from __future__ import annotations

"""Page-level multiprocessing for main-window single-line export.

Each page is independent: source image, PDIC, PageSection data, line crops and
optional per-page merge all belong to that page.  Workers therefore write only
page-unique files.  Shared ``QT/_file_log.txt`` remains coordinator-owned so
multiple processes never append to it concurrently.
"""

from concurrent.futures import FIRST_COMPLETED, CancelledError, ProcessPoolExecutor, wait
from multiprocessing import get_context
from pathlib import Path
import json
from typing import Any, Callable

from . import formats
from .page_sections import read_page_sections
from .processing import append_crop_log, resolve_crop_worker_count, split_single_lines
from .project_storage import crop_settings_path, qt_root
from .single_line_merge_settings import load_merge_by_page, merge_page_line_images


CROP_SETTINGS_FILENAME = "_CropSettings.json"
PARALLEL_WORKERS_KEY = "parallel_workers"


def configured_single_line_workers(project_root: Path) -> int:
    """Read the existing crop-settings worker control and resolve its process count."""
    path = crop_settings_path(Path(project_root), CROP_SETTINGS_FILENAME)
    configured: Any = 0
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                configured = payload.get(PARALLEL_WORKERS_KEY, 0)
        except (OSError, ValueError, TypeError):
            configured = 0
    return resolve_crop_worker_count(configured)


def single_line_page_job(
    project_root: str | Path,
    image_path: str | Path,
    page_index: int,
    settings: Any,
    output_dir: str | Path,
    merge_by_page: bool,
) -> tuple[int, str, list[Any], bool]:
    """Process one page in a spawn-safe worker and return coordinator metadata."""
    project_root = Path(project_root)
    image_path = Path(image_path)
    output_dir = Path(output_dir)
    entries = formats.read_pdic(formats.pdic_path(image_path))
    sections = read_page_sections(image_path)
    records = split_single_lines(
        image_path,
        entries,
        settings,
        output_dir,
        profile_page_index=int(page_index),
        page_sections=sections,
        write_manifest=False,  # 后期制作只输出图片，不生成 .PSWords。
    )
    merged = False
    if merge_by_page:
        merged = merge_page_line_images(
            image_path, records, output_dir, write_manifest=False,
        ) is not None
    return int(page_index), image_path.name, list(records), bool(merged)


def run_single_line_pages(
    project_root: Path,
    images: tuple[Path, ...],
    indices: tuple[int, ...],
    settings: Any,
    progress: Callable[[int, int, str, int, bool, int], None],
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> tuple[int, int, Path, bool, int]:
    """Run selected pages serially or in a spawn-based process pool.

    The returned worker count is the effective count for this batch.  The
    coordinator alone appends the shared crop log after each completed page.
    """
    project_root = Path(project_root)
    output_dir = qt_root(project_root) / "PSW"
    output_dir.mkdir(parents=True, exist_ok=True)
    merge_by_page = load_merge_by_page(project_root)
    total = len(indices)
    if total <= 0:
        return 0, 0, output_dir, merge_by_page, 1

    requested = configured_single_line_workers(project_root)
    workers = max(1, min(int(requested), total))
    total_records = 0
    completed = 0

    def consume(result: tuple[int, str, list[Any], bool]) -> None:
        nonlocal total_records, completed
        _page_index, filename, records, merged = result
        append_crop_log(project_root, records)
        total_records += len(records)
        completed += 1
        progress(completed, total, filename, len(records), merged, workers)

    if workers <= 1:
        for index in indices:
            if cancel_requested is not None and cancel_requested():
                raise CancelledError("单行切图已取消，已完成的页面保留")
            consume(single_line_page_job(
                project_root,
                images[index],
                index,
                settings,
                output_dir,
                merge_by_page,
            ))
        return total, total_records, output_dir, merge_by_page, 1

    # Only workers*2 futures are ever submitted. Queuing all selected pages
    # retains one Future/argument payload per page and delays cancellation.
    context = get_context("spawn")
    executor = ProcessPoolExecutor(max_workers=workers, mp_context=context)
    next_page = iter(indices)
    in_flight = set()
    inflight_limit = min(total, max(workers, workers * 2))

    def submit_ready() -> None:
        while len(in_flight) < inflight_limit:
            if cancel_requested is not None and cancel_requested():
                return
            try:
                index = next(next_page)
            except StopIteration:
                return
            in_flight.add(executor.submit(
                single_line_page_job,
                str(project_root),
                str(images[index]),
                int(index),
                settings,
                str(output_dir),
                bool(merge_by_page),
            ))

    try:
        submit_ready()
        while in_flight:
            if cancel_requested is not None and cancel_requested():
                raise CancelledError("单行切图已取消，已完成的页面保留")
            completed_futures, _ = wait(
                in_flight, timeout=0.1, return_when=FIRST_COMPLETED,
            )
            for future in completed_futures:
                in_flight.remove(future)
                consume(future.result())
            submit_ready()
    except BaseException:
        # Finish already-running page-level transactions safely. Stop accepting
        # new pages, and cancel queued work before returning control to the GUI.
        for future in in_flight:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)

    return total, total_records, output_dir, merge_by_page, workers


__all__ = [
    "PARALLEL_WORKERS_KEY",
    "configured_single_line_workers",
    "run_single_line_pages",
    "single_line_page_job",
]
