"""Evaluation against explicitly human-verified line annotations only.

Never compute Precision, Recall, F1 from a PDIC auto-baseline, unchanged
automatic export, or another model prediction masquerading as ground truth.
"""
from __future__ import annotations

from typing import Any

from .ordinary_unified_diff import _line_matches

TRUTH_SCHEMA = "picture-capture-human-reviewed-lines-v1"


def evaluate_ordinary_page(
    diagnostic: dict[str, Any],
    truth: dict[str, Any],
    *,
    tolerance_px: int = 12,
) -> dict[str, Any]:
    if truth.get("schema") != TRUTH_SCHEMA or truth.get("human_verified") is not True:
        raise ValueError(
            "缺少显式 human_verified=true 人工复核标签；"
            "不能用自动画线或未经确认的 PDIC 计算准确率"
        )
    old_size = tuple(diagnostic.get("image_size", ()) or ())
    truth_size = tuple(truth.get("image_size", ()) or ())
    if old_size and truth_size and old_size != truth_size:
        raise ValueError("人工标注与诊断的源图尺寸不一致")
    truth_lines = list(truth.get("lines", []) or [])
    produced = list(diagnostic.get("final_lines", []) or [])
    if not all(isinstance(item, dict) and "x" in item and "y" in item
               for item in truth_lines):
        raise ValueError("lines 中必须逐条提供 x/y 源图坐标")
    matched, missed, extras = _line_matches(
        truth_lines, produced, tolerance_px,
    )
    tp, fn, fp = len(matched), len(missed), len(extras)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall else 0.0
    )
    return {
        "schema": "picture-capture-verified-ordinary-evaluation-v1",
        "annotation_source": "explicit_human_reviewed_lines",
        "page_index": diagnostic.get("page_index"),
        "tolerance_px": tolerance_px,
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6), "f1": round(f1, 6),
        "false_positives": extras,
        "false_negatives": missed,
        "matching": "source_image_px_proximity",
        "auto_baseline_as_truth": False,
    }


__all__ = ["TRUTH_SCHEMA", "evaluate_ordinary_page"]
