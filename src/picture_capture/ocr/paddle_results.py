from __future__ import annotations

"""PaddleOCR result-container and geometry decoding without runtime engine init.

The legacy core injects current callbacks and model class at call time.
"""

from collections.abc import Callable
from typing import Any
import numpy as np

from .headword_models import OCRRecord


def _json_payload(result: Any) -> dict[str, Any]:
    payload = getattr(result, "json", result)
    if callable(payload):
        payload = payload()
    if not isinstance(payload, dict):
        raise RuntimeError("PaddleOCR 返回了无法解析的结果格式")
    nested = payload.get("res")
    return nested if isinstance(nested, dict) else payload


def extract_ocr_records(
    result: Any,
    *,
    payload_reader: Callable[[Any], dict[str, Any]] | None = None,
    record_type: type[OCRRecord] | None = None,
    np_module: Any = np,
) -> list[OCRRecord]:
    payload = (payload_reader or _json_payload)(result)
    raw_texts = payload.get("rec_texts")
    raw_scores = payload.get("rec_scores")
    raw_boxes = payload.get("rec_boxes")
    texts = list(raw_texts) if raw_texts is not None else []
    scores = list(raw_scores) if raw_scores is not None else []
    boxes = list(raw_boxes) if raw_boxes is not None else []
    if not boxes:
        raw_polygons = payload.get("rec_polys")
        polygons = list(raw_polygons) if raw_polygons is not None else []
        for polygon in polygons:
            array = np_module.asarray(polygon)
            boxes.append([array[:, 0].min(), array[:, 1].min(), array[:, 0].max(), array[:, 1].max()])
    records: list[OCRRecord] = []
    for text, score, box in zip(texts, scores, boxes):
        values = [int(round(float(value))) for value in list(box)]
        if len(values) != 4:
            continue
        x0, y0, x1, y1 = values
        if x1 <= x0 or y1 <= y0:
            continue
        records.append((record_type or OCRRecord)(str(text).strip(), float(score), (x0, y0, x1, y1)))
    return sorted(records, key=lambda item: (item.box[1], item.box[0]))

