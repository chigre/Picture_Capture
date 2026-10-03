from __future__ import annotations

"""Compare ordinary, OCR and combined entry detection without changing project data."""

import argparse
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import tempfile

from PIL import Image

from picture_capture.bootstrap.core import build_core_services


build_core_services()

from picture_capture.formats import pdic_path, read_pdic
from picture_capture.models import Entry, ProjectState
from picture_capture.page_sections import read_page_sections
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
    project_root: Path, modes: tuple[str, ...], pages: str = "", force_ocr: bool = False,
) -> dict[str, object]:
    project = ProjectState.open(project_root)
    indices = _indices(project, pages)
    filter_path = headword_filter_rules_path(project.root, HEADWORD_FILTER_RULES_FILENAME)
    report_pages = []
    totals = {
        mode: {"pages": 0, "gt_pages": 0, "exact": 0, "tp": 0, "fp": 0, "fn": 0}
        for mode in modes
    }

    with tempfile.TemporaryDirectory(prefix="picture-capture-benchmark-") as raw:
        temp_root = Path(raw)
        for index in indices:
            page = project.images[index]
            with Image.open(page) as opened:
                image = opened.convert("RGB")
            sections = read_page_sections(page)
            gt = read_pdic(pdic_path(page)) if pdic_path(page).exists() else []
            row: dict[str, object] = {
                "page_index": index + 1,
                "page": page.name,
                "ground_truth_count": len(gt),
                "modes": {},
                "pairwise": {},
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
                try:
                    entries, geometry = detect_entries(
                        image, settings,
                        paddle_cache_path=cache,
                        force_paddle_refresh=force_ocr,
                        paddle_filter_rules_path=filter_path,
                        profile_page_index=index,
                        page_sections=sections,
                    )
                    detected[mode] = (entries, geometry)
                    data: dict[str, object] = {"count": len(entries), "error": ""}
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
                    row["modes"][mode] = {"count": None, "error": str(exc)}

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
        }

    return {
        "format": "picture-capture-detection-benchmark-v1",
        "project": str(project.root),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "modes": list(modes),
        "summary": summary,
        "pages": report_pages,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--modes", default=",".join(MODES))
    parser.add_argument("--pages", default="")
    parser.add_argument("--force-ocr", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    modes = tuple(value.strip() for value in args.modes.split(",") if value.strip())
    invalid = [value for value in modes if value not in MODES]
    if invalid:
        parser.error("invalid mode(s): " + ", ".join(invalid))
    result = benchmark(args.project, modes or MODES, args.pages, args.force_ocr)
    output = args.output or Path.cwd() / (
        "detection_benchmark_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
    )
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
