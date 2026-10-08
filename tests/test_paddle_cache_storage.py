from __future__ import annotations

import json
from pathlib import Path

import picture_capture.paddle_headwords as ph
from picture_capture import paddle_cache_storage


def test_phase7p_cache_public_wrappers_keep_historical_core_path() -> None:
    assert ph.compact_ocr_cache_payload.__module__ == "picture_capture.paddle_headwords_core"
    assert ph.compact_ocr_cache_file.__module__ == "picture_capture.paddle_headwords_core"
    assert paddle_cache_storage.compact_ocr_cache_payload_impl.__module__.endswith(
        "paddle_cache_storage"
    )


def test_phase7p_atomic_json_uses_current_core_text_writer(tmp_path: Path, monkeypatch) -> None:
    seen = {}

    def fake_write(path: Path, text: str, *, encoding: str = "utf-8") -> None:
        seen["path"] = Path(path)
        seen["payload"] = text
        seen["encoding"] = encoding

    monkeypatch.setattr(ph, "_atomic_write_text", fake_write)
    target = tmp_path / "cache.json"

    ph._core._atomic_write_json(target, {"word": "café"})

    assert seen["path"] == target
    assert json.loads(seen["payload"]) == {"word": "café"}
    assert seen["encoding"] == "utf-8"


def test_phase7p_cache_payload_uses_current_core_candidate_compactor(monkeypatch) -> None:
    seen = []

    def fake_compact(row):
        seen.append(row)
        return {"patched": row.get("box")}

    monkeypatch.setattr(ph, "_compact_cached_candidate", fake_compact)
    payload = {
        "columns": [{
            "column": 0,
            "ocr_records": [],
            "candidates": [{"box": [1, 2, 3, 4]}],
        }],
    }

    compact = ph.compact_ocr_cache_payload(payload)

    assert seen == [{"box": [1, 2, 3, 4]}]
    assert compact["columns"][0]["candidates"] == [{"patched": [1, 2, 3, 4]}]


def test_phase7p_cache_file_uses_current_core_payload_and_json_hooks(
    tmp_path: Path, monkeypatch,
) -> None:
    cache = tmp_path / "page.json"
    cache.write_text('{"columns":[]}', encoding="utf-8")
    seen = {}

    def fake_payload(payload):
        seen["input"] = payload
        return {"patched": True}

    def fake_write(path: Path, payload: dict) -> None:
        seen["write_path"] = Path(path)
        seen["output"] = payload
        Path(path).write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(ph, "compact_ocr_cache_payload", fake_payload)
    monkeypatch.setattr(ph, "_atomic_write_json", fake_write)

    before, after, removed = ph.compact_ocr_cache_file(cache)

    assert seen["input"] == {"columns": []}
    assert seen["write_path"] == cache
    assert seen["output"] == {"patched": True}
    assert json.loads(cache.read_text(encoding="utf-8")) == {"patched": True}
    assert before > 0
    assert after > 0
    assert removed == 0
