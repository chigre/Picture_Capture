from __future__ import annotations

"""Persist the exact automatic marker set before later manual PDIC edits.

Batch ordinary drawing writes its snapshot explicitly from the spawn-safe worker.
The GUI also installs a conservative ``formats.write_pdic`` wrapper for direct
(non-worker) automatic writes.  That wrapper only creates a missing snapshot;
it never replaces an existing baseline during later manual editing.  A genuine
new batch automatic run explicitly replaces the snapshot before writing PDIC.

If a historical project has no snapshot, the training exporter can still
recompute an ordinary baseline non-destructively and marks that provenance
explicitly.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json

from .models import Entry


AUTO_BASELINE_FORMAT = "picture-capture-auto-baseline-v1"


def baseline_path_for_pdic(path: Path) -> Path:
    path = Path(path)
    return path.with_name(f"{path.stem}.auto-baseline.json")


def _entry_runtime_evidence(entry: Entry) -> bool:
    return bool(
        str(getattr(entry, "ocr_source", "") or "")
        or str(getattr(entry, "issue_type", "") or "")
        or getattr(entry, "confidence", None) is not None
        or str(getattr(entry, "candidate_id", "") or "")
        or bool(getattr(entry, "manually_selected", False))
    )


def automatic_entry_rows(entries: list[Entry]) -> list[dict[str, Any]]:
    return [
        {
            "order": index,
            "word": str(entry.word or ""),
            "source_x": int(entry.x),
            "source_y": int(entry.y),
            "confidence": (
                float(entry.confidence) if entry.confidence is not None else None
            ),
            "ocr_source": str(entry.ocr_source or ""),
            "issue_type": str(entry.issue_type or ""),
            "candidate_id": str(entry.candidate_id or ""),
            "final_engine": str(entry.final_engine or ""),
        }
        for index, entry in enumerate(entries, 1)
    ]


def looks_like_automatic_result(entries: list[Entry]) -> bool:
    if not entries:
        return False
    evidenced = sum(_entry_runtime_evidence(entry) for entry in entries)
    return evidenced >= max(1, (len(entries) + 1) // 2)


def save_automatic_baseline(
    pdic_path: Path,
    entries: list[Entry],
    image_width: int,
    pages: tuple[str, str, str],
) -> Path:
    """Atomically replace the baseline; call only from a known automatic run."""
    target = baseline_path_for_pdic(pdic_path)
    payload = {
        "format": AUTO_BASELINE_FORMAT,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "pdic_path_name": Path(pdic_path).name,
        "image_width": int(image_width),
        "pages": list(pages),
        "entry_count": len(entries),
        "entries": automatic_entry_rows(entries),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(target)
    return target


def load_automatic_baseline(pdic_path: Path) -> dict[str, Any]:
    path = baseline_path_for_pdic(pdic_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict) or payload.get("format") != AUTO_BASELINE_FORMAT:
        return {}
    return payload


def build_write_pdic_capture(
    original_write_pdic: Callable[[Path, list[Entry], int, tuple[str, str, str]], bool | None],
):
    """Capture a missing direct-write baseline without clobbering later edits."""
    if bool(getattr(original_write_pdic, "_picture_capture_baseline_wrapper", False)):
        return original_write_pdic

    def write_pdic_with_baseline(
        path: Path,
        entries: list[Entry],
        image_width: int,
        pages: tuple[str, str, str],
    ) -> bool | None:
        snapshot = baseline_path_for_pdic(path)
        if not snapshot.exists() and looks_like_automatic_result(entries):
            save_automatic_baseline(path, entries, image_width, pages)
        return original_write_pdic(path, entries, image_width, pages)

    setattr(write_pdic_with_baseline, "_picture_capture_baseline_wrapper", True)
    setattr(write_pdic_with_baseline, "_original_write_pdic", original_write_pdic)
    return write_pdic_with_baseline
