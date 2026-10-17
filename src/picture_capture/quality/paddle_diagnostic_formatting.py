from __future__ import annotations

"""Implementation helpers for Paddle OCR diagnostic TSV formatting.

Historical formatter names and header constants remain in paddle_headwords_core.
Core wrappers pass their current globals into these helpers at call time so the
public paddle_headwords assignment-mirroring contract remains effective.
"""

from typing import Any, Callable


def tsv_clean_impl(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = ",".join(str(x) for x in value)
    return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")


def candidate_reason_impl(cand: dict[str, Any]) -> str:
    reasons = []
    if cand.get("reject_reason"):
        reasons.append(str(cand.get("reject_reason")))
    if cand.get("parser_stage"):
        reasons.append("stage=" + str(cand.get("parser_stage")))
    bugs = list(cand.get("bug_types", []) or [])
    if bugs:
        reasons.append("bug=" + ",".join(str(x) for x in bugs))
    trace = list(cand.get("parser_trace", []) or [])
    if trace:
        reasons.append("trace=" + ">".join(str(x) for x in trace[:8]))
    if cand.get("alphabetical_warning"):
        reasons.append("WARN:" + str(cand.get("alphabetical_warning")))
    return ";".join(reasons)


def candidate_tsv_row_impl(
    column: int,
    cand: dict[str, Any],
    raw_status: str | None = None,
    engine: str = "",
    extra_reason: str = "",
    *,
    clean: Callable[[Any], str],
    reason_builder: Callable[[dict[str, Any]], str],
) -> str:
    status = raw_status if raw_status is not None else (
        "accept" if cand.get("accepted") else "reject"
    )
    reason_parts: list[str] = []
    if engine:
        reason_parts.append(f"engine={engine}")
    if raw_status == "raw":
        reason_parts.append("record=raw")
    elif raw_status == "rescued":
        reason_parts.append("record=rescued")
    elif raw_status == "error":
        reason_parts.append("record=error")
    else:
        reason_parts.append("record=candidate")
    candidate_reason = reason_builder(cand)
    if candidate_reason:
        reason_parts.append(candidate_reason)
    if extra_reason:
        reason_parts.append(extra_reason)
    values = [
        column,
        cand.get("box", ""),
        f"{float(cand.get('confidence', 0.0)):.4f}"
        if cand.get("confidence") is not None else "",
        cand.get("text", ""),
        status,
        cand.get("score", ""),
        cand.get("normalized_headword", ""),
        cand.get("raw_headword", ""),
        cand.get("corrected_headword", ""),
        cand.get("pos_cue", ""),
        ";".join(str(x) for x in cand.get("ocr_repairs", []) or []),
        ";".join(reason_parts),
    ]
    return "\t".join(clean(v) for v in values)


def diagnostic_text_impl(
    report_columns: list[dict[str, Any]],
    *,
    header: str,
    candidate_rows: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    candidate_row: Callable[..., str],
    clean: Callable[[Any], str],
) -> str:
    rows: list[str] = [header]
    for col in report_columns:
        n = int(col.get("column", 0)) + 1

        for rec in col.get("ocr_records", []):
            raw = {
                "box": rec.get("box"),
                "confidence": rec.get("confidence"),
                "text": rec.get("text", ""),
            }
            rows.append(candidate_row(n, raw, raw_status="raw", engine="PADDLE"))
        for cand in candidate_rows(col.get("candidates", [])):
            rows.append(candidate_row(n, cand, engine="PADDLE"))

        tess = col.get("tesseract", {}) or {}
        if tess.get("error"):
            rows.append(candidate_row(
                n,
                {"text": ""},
                raw_status="error",
                engine="TESSERACT",
                extra_reason="error=" + clean(tess.get("error")),
            ))
        else:
            for rec in tess.get("records", []):
                raw = {
                    "box": rec.get("box"),
                    "confidence": rec.get("confidence"),
                    "text": rec.get("text", ""),
                }
                rows.append(candidate_row(
                    n, raw, raw_status="raw", engine="TESSERACT"
                ))
        for cand in candidate_rows(tess.get("candidates", [])):
            rows.append(candidate_row(n, cand, engine="TESSERACT"))

        lens = col.get("lens", {}) or {}
        if lens.get("error"):
            rows.append(candidate_row(
                n, {"text": ""}, raw_status="error", engine="GOOGLE_LENS",
                extra_reason="error=" + clean(lens.get("error")),
            ))
        else:
            for rec in lens.get("records", []):
                raw = {
                    "box": rec.get("box"),
                    "confidence": rec.get("confidence"),
                    "text": rec.get("text", ""),
                }
                rows.append(candidate_row(
                    n, raw, raw_status="raw", engine="GOOGLE_LENS"
                ))
        for cand in candidate_rows(lens.get("candidates", [])):
            rows.append(candidate_row(n, cand, engine="GOOGLE_LENS"))

        for item in col.get("tesseract_rescued", []) or []:
            if isinstance(item, dict):
                rescue = {
                    "box": item.get("box", ""),
                    "confidence": item.get("confidence"),
                    "text": item.get("word", ""),
                    "score": item.get("score", ""),
                    "normalized_headword": item.get("word", ""),
                    "raw_headword": item.get("raw_headword", ""),
                    "corrected_headword": item.get("corrected_headword", ""),
                    "pos_cue": item.get("pos_cue", ""),
                    "ocr_repairs": item.get("ocr_repairs", []),
                }
            else:
                rescue = {"text": str(item)}
            rows.append(candidate_row(
                n, rescue, raw_status="rescued", engine="TESSERACT"
            ))

    return "\n".join(rows) + "\n"


def comparison_text_impl(
    report_columns: list[dict[str, Any]],
    *,
    header: str,
    clean: Callable[[Any], str],
) -> str:
    rows: list[str] = [header]
    for col in report_columns:
        n = int(col.get("column", 0)) + 1
        for pair in col.get("ocr_y_comparison", []) or []:
            values = [
                n,
                pair.get("paddle_source_y"), pair.get("paddle_box"),
                pair.get("paddle_conf"),
                "accept" if pair.get("paddle_accepted") is True
                else ("reject" if pair.get("paddle_accepted") is False else ""),
                pair.get("paddle_score"), pair.get("paddle_lemma"),
                pair.get("paddle_raw"), pair.get("paddle_corrected"),
                pair.get("paddle_pos"), pair.get("paddle_repairs"),
                pair.get("paddle_text"),
                pair.get("tesseract_source_y"), pair.get("tesseract_box"),
                pair.get("tesseract_conf"),
                "accept" if pair.get("tesseract_accepted") is True
                else ("reject" if pair.get("tesseract_accepted") is False else ""),
                pair.get("tesseract_score"), pair.get("tesseract_lemma"),
                pair.get("tesseract_raw"), pair.get("tesseract_corrected"),
                pair.get("tesseract_pos"), pair.get("tesseract_repairs"),
                pair.get("tesseract_text"), pair.get("delta_y"),
                pair.get("lemma_compare"), pair.get("status_compare"),
                pair.get("reason"),
            ]
            rows.append("\t".join(clean(v) for v in values))
    return "\n".join(rows) + "\n"


def engines_long_text_impl(
    report_columns: list[dict[str, Any]],
    *,
    header: str,
    clean: Callable[[Any], str],
) -> str:
    rows = [header]
    for col in report_columns:
        column = int(col.get("column", 0)) + 1
        for candidate in col.get("review_candidates", []) or []:
            pair_id = candidate.get("candidate_id", "")
            for engine in ("paddle", "tesseract", "lens"):
                side = candidate.get(engine, {}) or {}
                if side.get("y") is None:
                    continue
                values = [
                    pair_id, column, side.get("source_y"), engine,
                    side.get("confidence"), side.get("text", ""),
                    side.get("lemma", ""), side.get("POS", ""),
                    side.get("score", ""), side.get("repairs", []),
                    side.get("parser_trace", []),
                    "1" if side.get("accepted") else "0",
                    side.get("reason", ""),
                ]
                rows.append("\t".join(clean(value) for value in values))
    return "\n".join(rows) + "\n"


def fusion_text_impl(
    review_candidates: list[dict[str, Any]],
    *,
    header: str,
    clean: Callable[[Any], str],
) -> str:
    rows = [header]
    for item in review_candidates:
        engines = [
            engine for engine in ("paddle", "tesseract", "lens")
            if (item.get(engine, {}) or {}).get("y") is not None
        ]
        values = [
            item.get("candidate_id", ""), int(item.get("column", 0)) + 1,
            item.get("source_y", ""), ",".join(engines),
            "1" if item.get("selected") else "0", item.get("word", ""),
            item.get("final_engine", ""), item.get("confidence", ""),
            item.get("score", ""), "1" if item.get("needs_review") else "0",
            item.get("issue_types", []), item.get("decision_reason", ""),
        ]
        rows.append("\t".join(clean(value) for value in values))
    return "\n".join(rows) + "\n"


def issues_text_impl(
    review_candidates: list[dict[str, Any]],
    *,
    header: str,
    clean: Callable[[Any], str],
) -> str:
    rows = [header]
    for item in review_candidates:
        issues = list(item.get("issue_types", []) or [])
        if not issues:
            continue
        p = item.get("paddle", {}) or {}
        t = item.get("tesseract", {}) or {}
        lens = item.get("lens", {}) or {}
        values = [
            item.get("candidate_id"), int(item.get("column", 0)) + 1,
            item.get("source_y"), "1" if item.get("selected") else "0",
            item.get("word"), item.get("final_engine"), item.get("confidence"),
            item.get("score"), ",".join(issues), p.get("lemma"),
            t.get("lemma"), lens.get("lemma"), p.get("text"),
            t.get("text"), lens.get("text"), item.get("decision_reason"),
        ]
        rows.append("\t".join(clean(v) for v in values))
    return "\n".join(rows) + "\n"
