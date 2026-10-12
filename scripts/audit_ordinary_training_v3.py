#!/usr/bin/env python3
"""Audit *captured ordinary auto baselines*, not saved historic OCR caches.

For Picture Capture training-v3 archives, the authoritative comparison is:
artifacts/<stem>_auto_baseline.json (captured at automatic drawing) versus
annotations/<stem>.json (user's subsequently saved PDIC). The report is NOT
a fresh detection run of the currently checked-out branch.

Usage: python scripts/audit_ordinary_training_v3.py ...zip --output audit.json
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import zipfile


def ordered_alignment(
    predictions: list[dict], truth: list[dict], tolerance: int,
    column_starts: list[int] | None = None,
) -> tuple[int, list[dict], list[dict]]:
    """One-to-one same-column order-preserving alignment, maximal TP first."""
    # Some training exports use a logical section number in the `column`
    # field even when entries span both physical columns (Nôm pages 1 and 3).
    # Normalize from source X and the actual recorded per-page column paths.
    def normalize(items: list[dict]) -> list[dict]:
        rows = []
        for item in items:
            value = dict(item)
            if column_starts:
                value["physical_column"] = min(
                    range(len(column_starts)),
                    key=lambda i: abs(int(value["source_x"]) - column_starts[i]),
                )
            else:
                value["physical_column"] = int(value["column"])
            rows.append(value)
        return sorted(rows, key=lambda q: (q["physical_column"], q["source_y"]))

    a, b = normalize(predictions), normalize(truth)
    n, m = len(a), len(b)
    dp = [[(0, 0, ()) for _ in range(m + 1)] for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best = max(dp[i - 1][j], dp[i][j - 1], key=lambda x: x[:2])
            if a[i - 1]["physical_column"] == b[j - 1]["physical_column"]:
                distance = abs(a[i - 1]["source_y"] - b[j - 1]["source_y"])
                if distance <= tolerance:
                    prev = dp[i - 1][j - 1]
                    candidate = (
                        prev[0] + 1, prev[1] - distance,
                        prev[2] + ((i - 1, j - 1),),
                    )
                    if candidate[:2] > best[:2]:
                        best = candidate
            dp[i][j] = best
    matches = dp[n][m][2]
    used_a, used_b = {i for i, _j in matches}, {j for _i, j in matches}
    return len(matches), [
        item for i, item in enumerate(a) if i not in used_a
    ], [item for i, item in enumerate(b) if i not in used_b]


def audit_archive(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read("dataset_manifest.json"))
        if manifest.get("format") != "picture-capture-training-v3":
            raise ValueError(f"Not a training-v3 ZIP: {path}")
        settings = manifest["settings"]
        tolerance = max(8, round(float(settings.get("character_height", 26)) * .5))
        pages = []
        for record in manifest["page_records"]:
            name = Path(record["page"]).stem
            annotation = json.loads(z.read(record["annotation"]))
            snapshot = json.loads(z.read(f"artifacts/{name}_auto_baseline.json"))
            if snapshot.get("provenance") != "captured_at_automatic_draw":
                raise ValueError(f"Non-historic baseline provenance: {path}/{name}")
            truth = annotation["ground_truth_lines"]
            predicted = snapshot["entries"]
            source_paths = annotation.get("layout", {}).get("source_column_paths_xy", [])
            column_starts = [int(points[0][0]) for points in source_paths if points]
            matched, fp, fn = ordered_alignment(
                predicted, truth, tolerance, column_starts,
            )
            pages.append({
                "page": record["page"],
                "TP": matched, "FP": len(fp), "FN": len(fn),
                "predicted": len(predicted), "reference": len(truth),
                "auto_by_column": dict(Counter(str(min(
                    range(len(column_starts)),
                    key=lambda i: abs(int(item["source_x"]) - column_starts[i]),
                )) for item in predicted)) if column_starts else {},
                "reference_by_column": dict(Counter(str(min(
                    range(len(column_starts)),
                    key=lambda i: abs(int(item["source_x"]) - column_starts[i]),
                )) for item in truth)) if column_starts else {},
                "false_positive": fp, "false_negative": fn,
                "diagnostic_layout": annotation.get("page_understanding_diagnostics", {}).get("layout", {}),
                "independent_page_design": annotation.get("page_design_diagnostics", {}),
            })
        tp = sum(item["TP"] for item in pages)
        fp = sum(item["FP"] for item in pages)
        fn = sum(item["FN"] for item in pages)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        return {
            "archive": path.name, "project": manifest["project_name"],
            "software_version": manifest.get("software_version"),
            "mode": settings.get("detection_method"),
            "pages": len(pages), "character_height": settings.get("character_height"),
            "matching_tolerance_px": tolerance, "TP": tp, "FP": fp, "FN": fn,
            "precision": p, "recall": r,
            "F1": 2*p*r/(p+r) if p+r else 0.0,
            "baseline": "captured_at_automatic_draw",
            "warning": "Not regenerated by the current PR branch; saved PDIC may be incomplete",
            "page_results": pages,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = [audit_archive(path) for path in args.archives]
    result = {
        "format": "picture-capture-ordinary-v3-baseline-audit-v1",
        "scope": "saved_real_scan_ordinary_baselines_only",
        "datasets": results,
        "totals": {key: sum(item[key] for item in results) for key in ("pages", "TP", "FP", "FN")},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for d in results:
        print(f'{d["project"]}: {d["pages"]}页  TP={d["TP"]} FP={d["FP"]} FN={d["FN"]}  F1={d["F1"]:.4f}')


if __name__ == "__main__":
    main()
