#!/usr/bin/env python3
"""Audit real Picture Capture training ZIPs against their saved OCR results.

Each training archive contains actual page images, human-confirmed PDIC, and
historic OCR candidate/final-entry JSON. This evaluates those *cached historic*
results; it does NOT rerun current main or the feature branch image detectors.

Image-only ZIPs receive a readability/dimension audit, never an invented F1.

Example:
  python scripts/benchmark_training_archives.py \
    "葡汉10页_training_20260930_143912_015887(1).zip" \
    "三民10页_training_20260930_144526_612835(1).zip" \
    "新时代西汉10页_training_20260930_145608_921889(1).zip" \
    "FarEast_0001-0020.zip" "DICs_for_test(1).zip" \
    --output training_archive_audit.json
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import io
import json
from pathlib import Path
import statistics
import sys
import zipfile

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from picture_capture.quality.ordered_marker_matching import match_ordered_markers


def _score(predicted: list[tuple], reference: list[tuple], tolerance: int) -> dict:
    predicted = sorted(predicted, key=lambda x: (x[0], x[1]))
    reference = sorted(reference, key=lambda x: (x[0], x[1]))
    admissible = [
        (abs(p[1] - r[1]), i, j)
        for i, p in enumerate(predicted)
        for j, r in enumerate(reference)
        if p[0] == r[0] and abs(p[1] - r[1]) <= tolerance
    ]
    pairs = match_ordered_markers(len(predicted), len(reference), admissible)
    pi, ri = {i for i, _ in pairs}, {j for _, j in pairs}
    displacement = [abs(predicted[i][1] - reference[j][1]) for i, j in pairs]

    # Historical greedy's best-cardinality loss is a useful diagnostic, but
    # differences in F1 MUST NOT be misrepresented as a detector improvement.
    greedy_i, greedy_j = set(), set()
    for _delta, i, j in sorted(admissible):
        if i not in greedy_i and j not in greedy_j:
            greedy_i.add(i)
            greedy_j.add(j)
    return {
        "truth": len(reference),
        "historic_cached_predictions": len(predicted),
        "TP": len(pairs), "FP": len(predicted) - len(pairs),
        "FN": len(reference) - len(pairs),
        "greedy_TP": len(greedy_i),
        "greedy_cardinality_loss": len(pairs) - len(greedy_i),
        "median_abs_y": statistics.median(displacement) if displacement else None,
        "unmatched_predictions": [
            {"column": p[0], "y": p[1], "word": p[2]}
            for i, p in enumerate(predicted) if i not in pi
        ],
        "unmatched_truth": [
            {"column": r[0], "y": r[1], "word": r[2]}
            for j, r in enumerate(reference) if j not in ri
        ],
    }


def _image_info(data: bytes) -> dict:
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        size = list(image.size)
        mode = image.mode
    return {"width": size[0], "height": size[1], "mode": mode}


def _training(archive: zipfile.ZipFile, source: str) -> dict:
    manifest = json.loads(archive.read("dataset_manifest.json"))
    settings = manifest["settings"]
    tolerance = max(1, round(float(settings.get("character_height", 26)) * .75))
    records = []
    for i in range(1, int(manifest.get("page_count", 0)) + 1):
        stem = f"{i:04d}"
        annotation = json.loads(archive.read(f"annotations/{stem}.json"))
        cache = json.loads(archive.read(f"ocr/{stem}.json"))
        gt = annotation["ground_truth_lines"]
        expected = [(str(item["word"]), int(item["source_x"]), int(item["source_y"])) for item in gt]
        pdic = []
        for line in archive.read(f"artifacts/{stem}.pdic").decode("utf-8-sig").splitlines():
            if line.strip():
                fields = line.split("#")
                pdic.append((fields[0], int(fields[1]), int(fields[2])))
        if Counter(expected) != Counter(pdic):
            raise ValueError(f"{source}/{stem}: PDIC annotations do not match saved markers")

        reference = [(int(item["column"]), int(item["source_y"]), str(item["word"])) for item in gt]
        positions = defaultdict(list)
        for item in gt:
            positions[int(item["column"])].append(int(item["source_x"]))
        lane_x = {k: statistics.median(v) for k, v in positions.items()}
        predicted = []
        for item in cache.get("final_entries", []):
            px = int(item["x"])
            column = min(lane_x, key=lambda c: abs(px - lane_x[c])) if lane_x else 0
            predicted.append((column, int(item["y"]), str(item.get("word", ""))))
        scores = _score(predicted, reference, tolerance)
        image_file = annotation["image"]["file"]
        info = _image_info(archive.read(image_file))
        if (info["width"], info["height"]) != (
            int(annotation["image"]["width"]), int(annotation["image"]["height"])
        ):
            raise ValueError(f"{source}/{stem}: source image dimensions disagree with annotations")
        scores.update({
            "page": stem, "image": image_file, "image_info": info,
            "OCR_candidates": len(cache.get("review_candidates", [])),
            "suspicious_labels": [
                {"column": v["column"], "y": v["source_y"], "word": v["word"]}
                for v in gt if not str(v["word"]).strip() or any(ch.isspace() for ch in str(v["word"]))
            ],
        })
        records.append(scores)

    tp, fp, fn = (sum(r[key] for r in records) for key in ("TP", "FP", "FN"))
    precision = tp / (tp + fp) if tp + fp else 0.
    recall = tp / (tp + fn) if tp + fn else 0.
    return {
        "archive": source, "kind": "historic_training_cache",
        "project": manifest.get("project_name"),
        "warning": "Does NOT measure current main or upgrade branch output",
        "tolerance_pixels": tolerance, "pages": len(records),
        "reference": tp + fn, "cached_predictions": tp + fp,
        "TP": tp, "FP": fp, "FN": fn,
        "precision": round(precision, 5), "recall": round(recall, 5),
        "F1": round(2 * precision * recall / (precision + recall), 5) if precision + recall else 0.,
        "greedy_match_loss": sum(p["greedy_cardinality_loss"] for p in records),
        "per_page": records,
    }


def _unlabelled(archive: zipfile.ZipFile, source: str) -> dict:
    image_names = sorted(
        name for name in archive.namelist()
        if name.lower().endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff"))
    )
    valid = []
    failures = []
    for name in image_names:
        try:
            info = _image_info(archive.read(name))
            valid.append({"file": name, **info})
        except (OSError, ValueError, EOFError) as exc:
            failures.append({"file": name, "error": str(exc)})
    return {
        "archive": source, "kind": "image_only_no_ground_truth",
        "images": len(image_names), "readable": len(valid),
        "failures": failures, "image_info": valid,
        "warning": "Cannot compute TP/FP/FN, no human PDIC markers in archive",
    }


def audit(paths: list[Path]) -> dict:
    datasets = []
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            if "dataset_manifest.json" in archive.namelist():
                datasets.append(_training(archive, path.name))
            else:
                datasets.append(_unlabelled(archive, path.name))
    labelled = [d for d in datasets if d["kind"] == "historic_training_cache"]
    tp, fp, fn = (sum(d[key] for d in labelled) for key in ("TP", "FP", "FN"))
    precision = tp / (tp + fp) if tp + fp else 0.
    recall = tp / (tp + fn) if tp + fn else 0.
    return {
        "format": "picture-capture-archive-audit-v1",
        "run_type": "historic_cache",
        "ground_truth_status": "saved_training_annotation_and_pdic",
        "algorithm": "ordered_max_cardinality_min_delta_v1",
        "evaluates": "historic_cached_final_entries_only",
        "all_archives": len(paths),
        "labelled_pages": sum(d["pages"] for d in labelled),
        "unlabelled_images": sum(d["images"] for d in datasets if d["kind"] != "historic_training_cache"),
        "TP": tp, "FP": fp, "FN": fn,
        "precision": round(precision, 5), "recall": round(recall, 5),
        "F1": round(2 * precision * recall / (precision + recall), 5) if precision + recall else 0.,
        "datasets": datasets,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.archives)
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(json.dumps({
        **{k: report[k] for k in (
            "labelled_pages", "unlabelled_images", "TP", "FP", "FN", "F1",
        )},
        "datasets": [
            {
                "archive": d["archive"], "kind": d["kind"],
                "F1": d.get("F1"), "FP": d.get("FP"), "FN": d.get("FN"),
                "readable": d.get("readable"),
            } for d in report["datasets"]
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
