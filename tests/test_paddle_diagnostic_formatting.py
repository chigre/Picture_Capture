from __future__ import annotations

import picture_capture.paddle_headwords as ph
from picture_capture import paddle_diagnostic_formatting


def _column_counts(text: str) -> list[int]:
    return [len(line.split("\t")) for line in text.rstrip("\n").splitlines()]


def test_phase7q_diagnostic_wrappers_keep_historical_core_path() -> None:
    for name in (
        "_tsv_clean",
        "_candidate_reason",
        "_candidate_tsv_row",
        "_diagnostic_text",
        "_comparison_text",
        "_engines_long_text",
        "_fusion_text",
        "_issues_text",
    ):
        assert getattr(ph, name).__module__ == "picture_capture.paddle_headwords_core"
    assert paddle_diagnostic_formatting.diagnostic_text_impl.__module__.endswith(
        "paddle_diagnostic_formatting"
    )


def test_phase7q_diagnostic_text_uses_current_core_candidate_hooks(monkeypatch) -> None:
    seen = []

    def fake_rows(rows):
        seen.append(("rows", list(rows)))
        return [{"text": "patched"}] if rows else []

    def fake_row(column, cand, raw_status=None, engine="", extra_reason=""):
        seen.append(("row", column, cand, raw_status, engine, extra_reason))
        return "PATCHED_ROW"

    monkeypatch.setattr(ph, "_candidate_rows", fake_rows)
    monkeypatch.setattr(ph, "_candidate_tsv_row", fake_row)

    text = ph._diagnostic_text([{
        "column": 0,
        "ocr_records": [],
        "candidates": [{"text": "original"}],
        "tesseract": {},
        "lens": {},
    }])

    assert text.splitlines()[1:] == ["PATCHED_ROW"]
    assert any(item[0] == "row" and item[4] == "PADDLE" for item in seen)


def test_phase7q_comparison_uses_current_core_cleaner_and_header(monkeypatch) -> None:
    monkeypatch.setattr(ph, "_COMPARISON_HEADER", "CUSTOM_HEADER")
    monkeypatch.setattr(ph, "_tsv_clean", lambda value: f"<{value}>")
    pair = {
        "paddle_source_y": 1,
        "tesseract_source_y": 2,
    }

    text = ph._comparison_text([{"column": 0, "ocr_y_comparison": [pair]}])

    lines = text.splitlines()
    assert lines[0] == "CUSTOM_HEADER"
    assert lines[1].startswith("<1>\t<1>")


def test_phase7q_strict_diagnostic_and_comparison_column_counts() -> None:
    row = ph._candidate_tsv_row(
        1,
        {
            "box": [1, 2, 3, 4],
            "confidence": 0.9,
            "text": "word",
            "accepted": True,
            "normalized_headword": "word",
        },
        engine="PADDLE",
    )
    assert len(row.split("\t")) == 12

    comparison = ph._comparison_text([{
        "column": 0,
        "ocr_y_comparison": [{
            "paddle_source_y": 10,
            "tesseract_source_y": 12,
            "paddle_accepted": True,
            "tesseract_accepted": False,
        }],
    }])
    assert _column_counts(comparison) == [27, 27]


def test_phase7q_strict_engine_fusion_and_issue_column_counts() -> None:
    engines = ph._engines_long_text([{
        "column": 0,
        "review_candidates": [{
            "candidate_id": "c1",
            "paddle": {"y": 10, "source_y": 10, "accepted": True},
        }],
    }])
    assert _column_counts(engines) == [13, 13]

    fusion = ph._fusion_text([{
        "candidate_id": "c1",
        "column": 0,
        "source_y": 10,
        "selected": True,
        "word": "alpha",
        "paddle": {"y": 10},
    }])
    assert _column_counts(fusion) == [12, 12]

    issues = ph._issues_text([{
        "candidate_id": "c1",
        "column": 0,
        "source_y": 10,
        "selected": True,
        "word": "alpha",
        "issue_types": ["OCR_CONFLICT"],
        "paddle": {},
        "tesseract": {},
        "lens": {},
    }])
    assert _column_counts(issues) == [16, 16]
