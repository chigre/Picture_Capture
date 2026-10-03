from __future__ import annotations

"""Benchmark saved detection decisions against Picture Capture training exports.

Training export v2 already records the user-confirmed PDIC lines together with
OCR review candidates and candidate-to-ground-truth matching.  This script turns
that annotation contract into a reproducible supervised benchmark without
rerunning OCR or modifying the source project.

Examples::

    uv run python scripts/training_export_benchmark.py export.zip
    uv run python scripts/training_export_benchmark.py a.zip b.zip --output report.json
"""

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import zipfile


@dataclass(slots=True)
class ExportSummary:
    name: str
    ground_truth: int
    matched_ground_truth: int
    no_candidate_misses: int
    true_positive: int
    false_positive: int
    candidate_false_negative: int
    true_negative_candidate: int
    fn_reasons: Counter[str]
    fp_reasons: Counter[str]
    page_rows: list[dict[str, object]]

    def as_dict(self) -> dict[str, object]:
        precision = (
            self.true_positive / (self.true_positive + self.false_positive)
            if self.true_positive + self.false_positive else 1.0
        )
        total_fn = self.candidate_false_negative + self.no_candidate_misses
        recall = (
            self.true_positive / (self.true_positive + total_fn)
            if self.true_positive + total_fn else 1.0
        )
        f1 = (
            2.0 * precision * recall / (precision + recall)
            if precision + recall else 0.0
        )
        coverage = (
            self.matched_ground_truth / self.ground_truth
            if self.ground_truth else 1.0
        )
        return {
            "export": self.name,
            "ground_truth": self.ground_truth,
            "matched_ground_truth": self.matched_ground_truth,
            "candidate_coverage": round(coverage, 6),
            "no_candidate_misses": self.no_candidate_misses,
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "candidate_false_negative": self.candidate_false_negative,
            "true_negative_candidate": self.true_negative_candidate,
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
            "fn_reasons": dict(self.fn_reasons.most_common()),
            "fp_reasons": dict(self.fp_reasons.most_common()),
            "pages": self.page_rows,
        }


def _candidate_reason(candidate: dict[str, object]) -> str:
    engine = str(candidate.get("final_engine") or "")
    side = candidate.get(engine) if engine else None
    if isinstance(side, dict):
        return str(side.get("reason") or "")
    return ""


def _ground_truth_key(page: str, candidate: dict[str, object]) -> tuple[str, int, int] | None:
    try:
        x = int(candidate.get("nearest_ground_truth_source_x"))
        y = int(candidate.get("nearest_ground_truth_source_y"))
    except (TypeError, ValueError):
        return None
    return page, x, y


def summarize_export(path: Path) -> ExportSummary:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    totals: Counter[str] = Counter()
    fn_reasons: Counter[str] = Counter()
    fp_reasons: Counter[str] = Counter()
    matched_ground_truth: set[tuple[str, int, int]] = set()
    ground_truth = 0
    page_rows: list[dict[str, object]] = []

    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("dataset_manifest.json"))
        if manifest.get("format") != "picture-capture-training-v2":
            raise ValueError(
                f"{path.name}: unsupported training format {manifest.get('format')!r}"
            )

        annotation_names = sorted(
            name for name in archive.namelist()
            if name.startswith("annotations/") and name.endswith(".json")
        )
        for annotation_name in annotation_names:
            annotation = json.loads(archive.read(annotation_name))
            page = str(annotation.get("page") or Path(annotation_name).stem)
            gt_rows = list(annotation.get("ground_truth_lines") or [])
            ground_truth += len(gt_rows)
            page_counts: Counter[str] = Counter()
            page_matched: set[tuple[str, int, int]] = set()

            candidates = list(
                (annotation.get("ocr_trace") or {}).get("candidates") or []
            )
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                # Original-Y fallbacks are editing alternatives for the same
                # physical OCR observation, not independent detection events.
                if str(candidate.get("position_variant", "refined")) != "refined":
                    continue

                selected = bool(candidate.get("selected"))
                gt_selected = bool(candidate.get("ground_truth_selected"))
                if selected and gt_selected:
                    label = "TP"
                elif selected and not gt_selected:
                    label = "FP"
                elif not selected and gt_selected:
                    label = "FN_candidate"
                else:
                    label = "TN_candidate"

                totals[label] += 1
                page_counts[label] += 1
                if gt_selected:
                    key = _ground_truth_key(page, candidate)
                    if key is not None:
                        matched_ground_truth.add(key)
                        page_matched.add(key)

                reason = _candidate_reason(candidate)
                if label == "FN_candidate":
                    fn_reasons[reason] += 1
                elif label == "FP":
                    fp_reasons[reason] += 1

            page_rows.append({
                "page": page,
                "ground_truth": len(gt_rows),
                "matched_ground_truth": len(page_matched),
                "no_candidate_misses": max(0, len(gt_rows) - len(page_matched)),
                "true_positive": page_counts["TP"],
                "false_positive": page_counts["FP"],
                "candidate_false_negative": page_counts["FN_candidate"],
                "true_negative_candidate": page_counts["TN_candidate"],
            })

    no_candidate = max(0, ground_truth - len(matched_ground_truth))
    return ExportSummary(
        name=path.name,
        ground_truth=ground_truth,
        matched_ground_truth=len(matched_ground_truth),
        no_candidate_misses=no_candidate,
        true_positive=totals["TP"],
        false_positive=totals["FP"],
        candidate_false_negative=totals["FN_candidate"],
        true_negative_candidate=totals["TN_candidate"],
        fn_reasons=fn_reasons,
        fp_reasons=fp_reasons,
        page_rows=page_rows,
    )


def aggregate(summaries: list[ExportSummary]) -> dict[str, object]:
    ground_truth = sum(item.ground_truth for item in summaries)
    matched = sum(item.matched_ground_truth for item in summaries)
    no_candidate = sum(item.no_candidate_misses for item in summaries)
    tp = sum(item.true_positive for item in summaries)
    fp = sum(item.false_positive for item in summaries)
    fn_candidate = sum(item.candidate_false_negative for item in summaries)
    tn = sum(item.true_negative_candidate for item in summaries)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn_candidate + no_candidate) if tp + fn_candidate + no_candidate else 1.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "exports": len(summaries),
        "ground_truth": ground_truth,
        "matched_ground_truth": matched,
        "candidate_coverage": round(matched / ground_truth, 6) if ground_truth else 1.0,
        "no_candidate_misses": no_candidate,
        "true_positive": tp,
        "false_positive": fp,
        "candidate_false_negative": fn_candidate,
        "true_negative_candidate": tn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark Picture Capture training-export decisions against saved PDIC ground truth."
    )
    parser.add_argument("exports", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    summaries = [summarize_export(path) for path in args.exports]
    report = {
        "format": "picture-capture-training-benchmark-v1",
        "aggregate": aggregate(summaries),
        "exports": [item.as_dict() for item in summaries],
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(args.output)
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
