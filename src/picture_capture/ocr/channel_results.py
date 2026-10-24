"""Paddle OCR result decoding and normalized channel materialization."""
from __future__ import annotations
from typing import Any, Iterable

def paddle_json_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        payload = result
    else:
        payload = getattr(result, "json", None)
        if callable(payload):
            payload = payload()
        if not isinstance(payload, dict):
            payload = getattr(result, "res", None)
        if not isinstance(payload, dict):
            raise RuntimeError("PaddleOCR 返回了无法解析的结果格式")
    nested = payload.get("res")
    return nested if isinstance(nested, dict) else payload

def normalize_paddle_result_impl(result: Any, *, payload_fn, np_module, record_cls) -> tuple[OcrChannelRecord, ...]:
    """Normalize one Paddle result using the mature runner's record semantics."""

    payload = payload_fn(result)
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
            boxes.append([
                array[:, 0].min(),
                array[:, 1].min(),
                array[:, 0].max(),
                array[:, 1].max(),
            ])

    records: list[OcrChannelRecord] = []
    for text, score, box in zip(texts, scores, boxes):
        try:
            values = [int(round(float(value))) for value in list(box)]
            confidence = float(score)
        except (TypeError, ValueError):
            continue
        if len(values) != 4:
            continue
        x0, y0, x1, y1 = values
        if x1 <= x0 or y1 <= y0:
            continue
        records.append(record_cls(
            str(text).strip(),
            confidence,
            (x0, y0, x1, y1),
        ))
    return tuple(sorted(records, key=lambda item: (item.box[1], item.box[0])))

def rescale_channel_records(
    records: Iterable[OcrChannelRecord],
    input_scale: float,
    *, record_cls,
) -> tuple[OcrChannelRecord, ...]:
    collected = tuple(records)
    if not collected or abs(float(input_scale) - 1.0) < 1e-9:
        return collected
    inverse = 1.0 / max(1e-9, float(input_scale))
    return tuple(
        record_cls(
            text=row.text,
            confidence=row.confidence,
            box=tuple(round(float(value) * inverse) for value in row.box),
        )
        for row in collected
    )

def candidate_from_records(
    engine: str,
    records: Iterable[OcrChannelRecord],
    *,
    text: str = "",
    metadata: dict[str, Any] | None = None,
    participates_in_fusion: bool = True,
    candidate_cls,
) -> OcrChannelCandidate:
    collected = tuple(records)
    final_text = str(text or "").strip()
    if not final_text:
        final_text = " ".join(item.text for item in collected if item.text).strip()
    confidence_values = [float(item.confidence) for item in collected]
    confidence = (
        sum(confidence_values) / len(confidence_values)
        if confidence_values else None
    )
    return candidate_cls(
        engine=engine,
        text=final_text,
        confidence=confidence,
        records=collected,
        participates_in_fusion=participates_in_fusion,
        metadata=dict(metadata or {}),
    )
