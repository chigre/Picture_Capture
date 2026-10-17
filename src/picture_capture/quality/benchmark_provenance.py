"""Provenance-safe, read-only summaries of existing Picture Capture benchmarks.

Historic OCR-cache F1 must never be presented as freshly regenerated detector
F1. Synthetic fixtures have no population-level accuracy or scanned pages.
"""
from __future__ import annotations

from typing import Any


REPORT_CONTRACT = "picture-capture-quality-report-v1"
SUPPORTED = {
    "picture-capture-detection-benchmark-v1": "current_detector",
    "picture-capture-archive-audit-v1": "historic_cache",
}


def _scores(row: dict[str, Any], *, historical: bool) -> dict[str, Any]:
    return {
        "tp": row.get("TP") if historical else row.get("true_positive"),
        "fp": row.get("FP") if historical else row.get("false_positive"),
        "fn": row.get("FN") if historical else row.get("false_negative"),
        "precision": row.get("precision"),
        "recall": row.get("recall"),
        "f1": row.get("F1") if historical else row.get("f1"),
    }


def quality_rows(report: dict[str, Any], *, label: str) -> list[dict[str, Any]]:
    """Never merge or relabel historical, regenerated and synthetic sources."""
    kind = SUPPORTED.get(report.get("format"))
    if kind is None:
        raise ValueError("Unsupported quality report format; refusing to infer provenance")
    explicit = report.get("run_type")
    if explicit is not None and explicit != kind:
        raise ValueError("Quality run_type contradicts its source report format")
    if kind == "current_detector":
        modes = report.get("summary")
        if not isinstance(modes, dict):
            raise ValueError("Current detector report has no per-mode summary")
        return [
            {
                "source": label,
                "run_type": kind,
                "mode": mode,
                "ground_truth_status": report.get(
                    "ground_truth_status", "saved_pdic_not_independently_verified"
                ),
                "gt_pages": row.get("ground_truth_pages", 0),
                **_scores(row, historical=False),
            }
            for mode, row in sorted(modes.items()) if isinstance(row, dict)
        ]
    datasets = report.get("datasets")
    if not isinstance(datasets, list):
        raise ValueError("Historical archive audit is missing datasets")
    return [
        {
            "source": label,
            "run_type": kind,
            "mode": "historic_cached_final_entries",
            "dictionary": row.get("project") or row.get("archive"),
            "ground_truth_status": "saved_training_annotation_and_pdic",
            "gt_pages": row.get("pages"),
            **_scores(row, historical=True),
        }
        for row in datasets if row.get("kind") == "historic_training_cache"
    ]


def build_quality_report(sources: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for label, report in sources:
        rows.extend(quality_rows(report, label=label))
    return {
        "format": REPORT_CONTRACT,
        "warning": (
            "Do not compare historical cache F1 to a current detector as a measured "
            "upgrade. Synthetic fixtures do not measure scanned-page accuracy."
        ),
        "rows": rows,
    }


def markdown_quality_report(report: dict[str, Any]) -> str:
    if report.get("format") != REPORT_CONTRACT:
        raise ValueError("Not a normalized quality report")
    lines = [
        "# Headword quality reports",
        "",
        "**Provenance warning:** Historic cached predictions, regenerated current "
        "detectors and synthetic fixtures are different evidence; never treat "
        "their F1 values as a before/after detector experiment.",
        "",
        "| Input | Run type | Dictionary / mode | GT pages | TP | FP | FN | F1 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["rows"]:
        def cell(key: str) -> str:
            value = row.get(key)
            return "—" if value is None else str(value).replace("|", "/").replace(chr(10), " ")
        name = row.get("dictionary") or row.get("mode") or "—"
        lines.append(
            f"| {cell('source')} | {cell('run_type')} | {name} | "
            f"{cell('gt_pages')} | {cell('tp')} | {cell('fp')} | "
            f"{cell('fn')} | {cell('f1')} |"
        )
    lines.extend(["", "See JSON `ground_truth_status` for whether labels were independently verified."])
    return chr(10).join(lines) + chr(10)
