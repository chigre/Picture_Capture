"""Optional, separately invalidated cache of *raw* Tesseract PSM records.

The main OCR cache currently only reuses Paddle records. Tesseract PSM 4/6
would rerun on every parser-only adjustment; this small engine-scoped sidecar
can reuse its exact pre-parser recognition records when explicitly enabled.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .formats import write_text_atomic


CACHE_FORMAT = "picture-capture-tesseract-raw-v1"


def tesseract_variant_path(ocr_cache_path: Path) -> Path:
    return ocr_cache_path.with_name(ocr_cache_path.stem + "_tesseract_raw_v1.json")


def _engine_key(
    source_signature: str, *, language: str, executable: str,
    auto_psm: bool, fixed_psm: int, vertical: bool,
    engine_status: dict[str, Any] | None,
) -> str:
    params = {
        "format": CACHE_FORMAT,
        "ocr_input_signature": str(source_signature),
        "language": str(language),
        "executable": str(executable),
        "auto_psm": bool(auto_psm),
        "fixed_psm": int(fixed_psm),
        "vertical": bool(vertical),
        # Includes the installed binary/version reported by availability
        # diagnostics. An unknown engine version should be a cache miss if its
        # availability report changes, not a silent reuse.
        "engine_status": engine_status or {},
    }
    return hashlib.sha256(
        json.dumps(params, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


class TesseractRawCache:
    def __init__(
        self, ocr_cache_path: Path, source_signature: str, *,
        language: str, executable: str, auto_psm: bool, fixed_psm: int,
        vertical: bool, engine_status: dict[str, Any] | None = None,
        force_refresh: bool = False,
    ):
        self.path = tesseract_variant_path(ocr_cache_path)
        self.key = _engine_key(
            source_signature, language=language, executable=executable,
            auto_psm=auto_psm, fixed_psm=fixed_psm, vertical=vertical,
            engine_status=engine_status,
        )
        self.records: dict[str, dict[str, Any]] = {}
        if not force_refresh and self.path.is_file():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if (
                    isinstance(payload, dict)
                    and payload.get("format") == CACHE_FORMAT
                    and payload.get("key") == self.key
                    and isinstance(payload.get("records"), dict)
                ):
                    self.records = dict(payload["records"])
            except (OSError, ValueError, TypeError):
                pass

    def read(self, column: int, psm: int) -> tuple[list[dict[str, Any]], str] | None:
        item = self.records.get(f"{int(column)}:{int(psm)}")
        if not isinstance(item, dict):
            return None
        records, text = item.get("records"), item.get("text")
        if not isinstance(records, list) or not isinstance(text, str):
            return None
        if not all(
            isinstance(r, dict) and isinstance(r.get("text"), str)
            and isinstance(r.get("confidence"), (int, float))
            and isinstance(r.get("box"), list) and len(r["box"]) == 4
            and all(isinstance(coord, int) for coord in r["box"])
            for r in records
        ):
            return None
        return list(records), text

    def record(
        self, column: int, psm: int,
        canonical_records: list[dict[str, Any]], text: str,
    ) -> None:
        self.records[f"{int(column)}:{int(psm)}"] = {
            "records": list(canonical_records), "text": str(text),
        }

    def save(self) -> None:
        payload = {
            "format": CACHE_FORMAT, "key": self.key, "records": self.records,
        }
        write_text_atomic(
            self.path,
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
