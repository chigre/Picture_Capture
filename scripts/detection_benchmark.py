from __future__ import annotations

"""Compare ordinary, OCR and combined entry detection without changing project data."""

import argparse
import cProfile
from dataclasses import replace
from datetime import datetime
from io import StringIO
import json
from pathlib import Path
import pstats
import tempfile
from time import perf_counter

from PIL import Image

from picture_capture.bootstrap.core import build_core_services


build_core_services()

from picture_capture.formats import pdic_path, read_pdic
from picture_capture.models import Entry, ProjectState
from picture_capture.page_sections import read_page_sections
from picture_capture.performance_metrics import timing_summary_ms
from picture_capture.processing import Geometry, column_index_for_click, detect_entries
from picture_capture.project_storage import headword_filter_rules_path
from picture_capture.paddle_headwords import HEADWORD_FILTER_RULES_FILENAME


MODES = ("left_edge", "paddleocr", "combined")


def _rows(entries: list[Entry], geometry: Geometry) -> list[tuple[int, int]]:
    result = []
    for entry in entries:
        _u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        col = column_index_for_click(int(entry.x), geometry, int(entry.y))
        result.append((int(col), int(v)))
    return sorted(result)


def match_markers(
    predicted: list[Entry], reference: list[Entry], geometry: Geometry, tolerance: int,
) -> dict[str, object]:
    """Globally match same-column markers by minimum absolute reading-axis distance."""
    pred = _rows(predicted, geometry)
    ref = _rows(reference, geometry)
    edges = []
    for pi, (pc, pv) in enumerate(pred):
        for ri, (rc, rv) in enumerate(ref):
            if pc != rc:
                continue
            delta = abs(pv - rv)
            if delta <= tolerance:
                edges.append((delta, pi, ri))
    edges.sort()

    used_p: set[int] = set()
    used_r: set[int] = set()
    deltas: list[int] = []
    for delta, pi, ri in edges:
        if pi in used_p or ri in used_r:
            continue
        used_p.add(pi); used_r.add(ri); deltas.append(delta)

    tp = len(deltas)
    fp = len(pred) - tp
    fn = len(ref) - tp
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    ordered = sorted(deltas)
    return {
        "predicted": len(pred),
        "reference": len(ref),
        "matched": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "exact": fp == 0 and fn == 0,
        "median_abs_delta_v": (
            ordered[len(ordered) // 2] if ordered else None
        ),
        "p95_abs_delta_v": (
            ordered[min(len(ordered) - 1, round((len(ordered) - 1) * .95))]
            if ordered else None
        ),
    }


def _indices(project: ProjectState, spec: str) -> list[int]:
    if not spec.strip():
        return list(range(len(project.images)))
    result: set[int] = set()
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            a, b = (int(value) for value in token.split("-", 1))
            lo, hi = sorted((max(1, a), min(len(project.images), b)))
            result.update(range(lo - 1, hi))
        else:
            value = int(token)
            if 1 <= value <= len(project.images):
                result.add(value - 1)
    return sorted(result)


def benchmark(
    project_root: Path,
    modes: tuple[str, ...],
    pages: str = "",
    force_ocr: bool = False,
    timing_repeats: int = 1,
) -> dict[str, object]:
    if timing_repeats < 1:
        raise ValueError("timing_repeats must be >= 1")

    benchmark_started = perf_counter()
    project_open_started = perf_counter()
    project = ProjectState.open(project_root)
    project_open_ms = round((perf_counter() - project_open_started) * 1000.0, 3)
    indices = _indices(project, pages)
    filter_path = headword_filter_rules_path(project.root, HEADWORD_FILTER_RULES_FILENAME)
    report_pages = []
    totals = {
        mode: {
            "pages": 0,
            "gt_pages": 0,
            "exact": 0,
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "timing_ms": [],
            "repeat_timing_ms": [],
        }
        for mode in modes
    }
    page_total_timings_ms: list[float] = []

    with tempfile.TemporaryDirectory(prefix="picture-capture-benchmark-") as raw:
        temp_root = Path(raw)
        for index in indices:
            page_started = perf_counter()
            page = project.images[index]

            image_load_started = perf_counter()
            with Image.open(page) as opened:
                image = opened.convert("RGB")
            image_load_ms = round((perf_counter() - image_load_started) * 1000.0, 3)

            metadata_started = perf_counter()
            sections = read_page_sections(page)
            gt = read_pdic(pdic_path(page)) if pdic_path(page).exists() else []
            metadata_io_ms = round((perf_counter() - metadata_started) * 1000.0, 3)

            row: dict[str, object] = {
                "page_index": index + 1,
                "page": page.name,
                "ground_truth_count": len(gt),
                "modes": {},
                "pairwise": {},
                "timing_ms": {
                    "image_load": image_load_ms,
                    "metadata_io": metadata_io_ms,
                    "pairwise_comparison": 0.0,
                    "page_total": 0.0,
                },
            }
            detected: dict[str, tuple[list[Entry], Geometry]] = {}

            for mode in modes:
                settings = replace(project.settings)
                settings.detection_method = mode
                cache = (
                    temp_root / mode / f"{page.stem}.json"
                    if mode in {"paddleocr", "combined"} else None
                )
                if cache is not None:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                cache_exists_before_first = bool(cache is not None and cache.exists())
                detect_started = perf_counter()
                try:
                    entries, geometry = detect_entries(
                        image, settings,
                        paddle_cache_path=cache,
                        force_paddle_refresh=force_ocr,
                        paddle_filter_rules_path=filter_path,
                        profile_page_index=index,
                        page_sections=sections,
                    )
                    detect_ms = round((perf_counter() - detect_started) * 1000.0, 3)
                    totals[mode]["timing_ms"].append(detect_ms)
                    detected[mode] = (entries, geometry)

                    timing_runs_ms = [detect_ms]
                    repeat_errors: list[str] = []
                    for _repeat_index in range(1, timing_repeats):
                        repeat_started = perf_counter()
                        try:
                            detect_entries(
                                image, settings,
                                paddle_cache_path=cache,
                                force_paddle_refresh=False,
                                paddle_filter_rules_path=filter_path,
                                profile_page_index=index,
                                page_sections=sections,
                            )
                            repeat_ms = round(
                                (perf_counter() - repeat_started) * 1000.0, 3
                            )
                            timing_runs_ms.append(repeat_ms)
                            totals[mode]["repeat_timing_ms"].append(repeat_ms)
                        except Exception as exc:
                            repeat_ms = round(
                                (perf_counter() - repeat_started) * 1000.0, 3
                            )
                            timing_runs_ms.append(repeat_ms)
                            totals[mode]["repeat_timing_ms"].append(repeat_ms)
                            repeat_errors.append(str(exc))
                            break

                    data: dict[str, object] = {
                        "count": len(entries),
                        "error": "",
                        "timing_ms": detect_ms,
                        "timing_runs_ms": timing_runs_ms,
                        "repeat_timing_ms": timing_summary_ms(timing_runs_ms[1:]),
                        "repeat_errors": repeat_errors,
                        "cache": {
                            "enabled": cache is not None,
                            "exists_before_first": cache_exists_before_first,
                            "exists_after_first": bool(
                                cache is not None and cache.exists()
                            ),
                            "first_run_force_refresh": bool(
                                cache is not None and force_ocr
                            ),
                            "repeat_force_refresh": False,
                        },
                    }
                    if gt:
                        tolerance = max(4, round(float(settings.character_height) * .45))
                        metrics = match_markers(entries, gt, geometry, tolerance)
                        data["ground_truth"] = metrics
                        total = totals[mode]
                        total["gt_pages"] += 1
                        total["exact"] += int(bool(metrics["exact"]))
                        total["tp"] += int(metrics["matched"])
                        total["fp"] += int(metrics["false_positive"])
                        total["fn"] += int(metrics["false_negative"])
                    row["modes"][mode] = data
                    totals[mode]["pages"] += 1
                except Exception as exc:
                    detect_ms = round((perf_counter() - detect_started) * 1000.0, 3)
                    totals[mode]["timing_ms"].append(detect_ms)
                    row["modes"][mode] = {
                        "count": None,
                        "error": str(exc),
                        "timing_ms": detect_ms,
                        "timing_runs_ms": [detect_ms],
                        "repeat_timing_ms": timing_summary_ms([]),
                        "repeat_errors": [],
                        "cache": {
                            "enabled": cache is not None,
                            "exists_before_first": cache_exists_before_first,
                            "exists_after_first": bool(
                                cache is not None and cache.exists()
                            ),
                            "first_run_force_refresh": bool(
                                cache is not None and force_ocr
                            ),
                            "repeat_force_refresh": False,
                        },
                    }

            pairwise_started = perf_counter()
            names = list(detected)
            for i, left in enumerate(names):
                for right in names[i + 1:]:
                    entries_l, geometry = detected[left]
                    entries_r, _ = detected[right]
                    tolerance = max(
                        4, round(float(project.settings.character_height) * .45)
                    )
                    row["pairwise"][f"{left}__vs__{right}"] = match_markers(
                        entries_l, entries_r, geometry, tolerance
                    )
            row["timing_ms"]["pairwise_comparison"] = round(
                (perf_counter() - pairwise_started) * 1000.0, 3
            )
            page_total_ms = round((perf_counter() - page_started) * 1000.0, 3)
            row["timing_ms"]["page_total"] = page_total_ms
            page_total_timings_ms.append(page_total_ms)
            report_pages.append(row)

    summary = {}
    for mode, total in totals.items():
        tp, fp, fn = total["tp"], total["fp"], total["fn"]
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall else None
        )
        gt_pages = total["gt_pages"]
        summary[mode] = {
            "pages_completed": total["pages"],
            "ground_truth_pages": gt_pages,
            "exact_ground_truth_pages": total["exact"],
            "exact_page_rate": round(total["exact"] / gt_pages, 6) if gt_pages else None,
            "precision": round(precision, 6) if precision is not None else None,
            "recall": round(recall, 6) if recall is not None else None,
            "f1": round(f1, 6) if f1 is not None else None,
            "false_positive": fp,
            "false_negative": fn,
            "timing_ms": timing_summary_ms(total["timing_ms"]),
            "repeat_timing_ms": timing_summary_ms(total["repeat_timing_ms"]),
        }

    return {
        "format": "picture-capture-detection-benchmark-v1",
        "project": str(project.root),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "modes": list(modes),
        "timing_repeats": timing_repeats,
        "summary": summary,
        "timing_ms": {
            "project_open": project_open_ms,
            "pages": timing_summary_ms(page_total_timings_ms),
            "benchmark_total": round((perf_counter() - benchmark_started) * 1000.0, 3),
        },
        "pages": report_pages,
    }



def warm_cpu_profiles(
    project_root: Path,
    modes: tuple[str, ...],
    pages: str,
    output_dir: Path,
) -> dict[str, object]:
    """Profile one warmed detection call per selected page/mode outside timing runs."""
    project = ProjectState.open(project_root)
    indices = _indices(project, pages)
    filter_path = headword_filter_rules_path(
        project.root, HEADWORD_FILTER_RULES_FILENAME
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    profiles: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="picture-capture-profile-") as raw:
        temp_root = Path(raw)
        for index in indices:
            page = project.images[index]
            with Image.open(page) as opened:
                image = opened.convert("RGB")
            sections = read_page_sections(page)

            for mode in modes:
                settings = replace(project.settings)
                settings.detection_method = mode
                cache = (
                    temp_root / mode / f"{page.stem}.json"
                    if mode in {"paddleocr", "combined"} else None
                )
                if cache is not None:
                    cache.parent.mkdir(parents=True, exist_ok=True)

                stem = f"{index + 1:04d}_{page.stem}__{mode}"
                profile_path = output_dir / f"{stem}.prof"
                summary_path = output_dir / f"{stem}.txt"
                item: dict[str, object] = {
                    "page_index": index + 1,
                    "page": page.name,
                    "mode": mode,
                    "cache_enabled": cache is not None,
                    "profile": str(profile_path),
                    "summary": str(summary_path),
                    "error": "",
                }

                try:
                    # Warm process/model state and, for OCR modes, populate the
                    # same temporary cache used by the profiled call.
                    detect_entries(
                        image,
                        settings,
                        paddle_cache_path=cache,
                        force_paddle_refresh=False,
                        paddle_filter_rules_path=filter_path,
                        profile_page_index=index,
                        page_sections=sections,
                    )

                    profiler = cProfile.Profile()
                    profiler.enable()
                    try:
                        detect_entries(
                            image,
                            settings,
                            paddle_cache_path=cache,
                            force_paddle_refresh=False,
                            paddle_filter_rules_path=filter_path,
                            profile_page_index=index,
                            page_sections=sections,
                        )
                    finally:
                        profiler.disable()

                    profiler.dump_stats(str(profile_path))
                    stream = StringIO()
                    pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats(
                        "cumulative"
                    ).print_stats(50)
                    summary_path.write_text(stream.getvalue(), encoding="utf-8")
                except Exception as exc:
                    item["error"] = str(exc)

                profiles.append(item)

    return {
        "mode": "warm",
        "profiled_calls_are_timing_samples": False,
        "profiles": profiles,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--modes", default=",".join(MODES))
    parser.add_argument("--pages", default="")
    parser.add_argument("--force-ocr", action="store_true")
    parser.add_argument(
        "--timing-repeats",
        type=int,
        default=1,
        help=(
            "run successful detection modes repeatedly for timing; "
            "repeat runs reuse the same cache with force-refresh disabled"
        ),
    )
    parser.add_argument(
        "--warm-cpu-profile-dir",
        type=Path,
        help=(
            "after benchmark timing, run one extra warmed cProfile call per "
            "page/mode and write .prof plus cumulative .txt summaries"
        ),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    modes = tuple(value.strip() for value in args.modes.split(",") if value.strip())
    invalid = [value for value in modes if value not in MODES]
    if invalid:
        parser.error("invalid mode(s): " + ", ".join(invalid))
    if args.timing_repeats < 1:
        parser.error("--timing-repeats must be >= 1")
    result = benchmark(
        args.project,
        modes or MODES,
        args.pages,
        args.force_ocr,
        timing_repeats=args.timing_repeats,
    )
    if args.warm_cpu_profile_dir is not None:
        result["warm_cpu_profiles"] = warm_cpu_profiles(
            args.project,
            modes or MODES,
            args.pages,
            args.warm_cpu_profile_dir,
        )
    output = args.output or Path.cwd() / (
        "detection_benchmark_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
    )
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
