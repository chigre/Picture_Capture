from __future__ import annotations

import json
from pathlib import Path

from picture_capture.quality import inference_monitor


def test_model_events_report_actual_constructor_arguments(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(inference_monitor, "_root", lambda: tmp_path)
    inference_monitor.record_model_event("TextDetection", "gpu", "auto", 4)
    inference_monitor.record_model_event("PaddleOCR", "cpu", "off", 2)
    rows = inference_monitor.recent_model_events(0)
    assert len(rows) == 2
    assert [row["kind"] for row in rows] == ["TextDetection", "PaddleOCR"]
    assert [row["device"] for row in rows] == ["gpu", "cpu"]
    assert rows[-1]["cpu_threads"] == 2
    assert all(isinstance(row["pid"], int) for row in rows)


def test_events_ignore_old_or_malformed_records(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(inference_monitor, "_root", lambda: tmp_path)
    (tmp_path / "invalid.jsonl").write_text("not json\\n", encoding="utf-8")
    assert inference_monitor.recent_model_events(0) == []
