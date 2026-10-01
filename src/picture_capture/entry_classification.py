from __future__ import annotations

"""Canonical per-entry classification shared by drawing, OCR crop and review.

PDIC remains unchanged for downstream compatibility.  Structural metadata is
stored in a project-local JSON sidecar and also kept in a lightweight runtime
registry keyed by the concrete Entry/LayoutLine object.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable
import json
import os
import tempfile

from .models import AppSettings, Entry

ENTRY_SOURCES = {"indent", "symbol_sample", "large_head", "ocr", "manual", "unknown"}
ENTRY_SCALES = {"regular", "oversized"}
SIDECAR_FORMAT = "picture-capture-entry-classification-v1"


@dataclass(slots=True)
class EntryClassification:
    entry_source: str = "unknown"
    entry_scale: str = "regular"
    detected_head_height: float = 0.0
    manual_override: bool = False
    auto_entry_source: str = "unknown"
    auto_entry_scale: str = "regular"

    def normalized(self) -> "EntryClassification":
        source = self.entry_source if self.entry_source in ENTRY_SOURCES else "unknown"
        scale = self.entry_scale if self.entry_scale in ENTRY_SCALES else "regular"
        auto_source = self.auto_entry_source if self.auto_entry_source in ENTRY_SOURCES else source
        auto_scale = self.auto_entry_scale if self.auto_entry_scale in ENTRY_SCALES else scale
        return EntryClassification(
            entry_source=source,
            entry_scale=scale,
            detected_head_height=max(0.0, float(self.detected_head_height or 0.0)),
            manual_override=bool(self.manual_override),
            auto_entry_source=auto_source,
            auto_entry_scale=auto_scale,
        )


_ENTRY_META: dict[int, EntryClassification] = {}
_LINE_META: dict[int, EntryClassification] = {}


def infer_entry_classification(entry: Entry) -> EntryClassification:
    source_text = str(getattr(entry, "ocr_source", "") or "")
    issue = str(getattr(entry, "issue_type", "") or "")
    oversized = bool(getattr(entry, "ocr_oversized_cjk", False))
    height = float(getattr(entry, "ocr_visual_run_height", 0.0) or 0.0)
    if "ordinary_large_head_evidence" in source_text or "OVERSIZED_DISPLAY_HEAD" in issue:
        source = "large_head"
        scale = "oversized"
    elif "ordinary_symbol_evidence" in source_text or "VISUAL_BRACKET_SAMPLE" in issue or "VISUAL_ENTRY_MARKER_SAMPLE" in issue:
        source = "symbol_sample"
        scale = "regular"
    elif "ordinary_layout_role" in source_text or "ORDINARY_LAYOUT_ROLE" in issue:
        source = "indent"
        scale = "regular"
    elif source_text:
        source = "ocr"
        scale = "oversized" if oversized else "regular"
    else:
        source = "unknown"
        scale = "oversized" if oversized else "regular"
    return EntryClassification(
        entry_source=source,
        entry_scale=scale,
        detected_head_height=max(0.0, height),
        manual_override=False,
        auto_entry_source=source,
        auto_entry_scale=scale,
    )


def get_entry_classification(entry: Entry) -> EntryClassification:
    current = _ENTRY_META.get(id(entry))
    if current is None:
        current = infer_entry_classification(entry)
        _ENTRY_META[id(entry)] = current
    return current.normalized()


def register_entry_classification(
    entry: Entry,
    *,
    entry_source: str | None = None,
    entry_scale: str | None = None,
    detected_head_height: float | None = None,
    manual_override: bool | None = None,
    auto_entry_source: str | None = None,
    auto_entry_scale: str | None = None,
) -> EntryClassification:
    prior = get_entry_classification(entry)
    auto_source = str(auto_entry_source or entry_source or prior.auto_entry_source or "unknown")
    auto_scale = str(auto_entry_scale or entry_scale or prior.auto_entry_scale or "regular")
    manual = prior.manual_override if manual_override is None else bool(manual_override)
    source = str(entry_source or prior.entry_source or auto_source)
    scale = str(entry_scale or prior.entry_scale or auto_scale)
    if manual and prior.manual_override and manual_override is None:
        # Automatic refreshes may update provenance/geometry but never overwrite
        # an explicit user scale choice.
        scale = prior.entry_scale
    meta = EntryClassification(
        entry_source=source,
        entry_scale=scale,
        detected_head_height=(
            prior.detected_head_height
            if detected_head_height is None
            else max(0.0, float(detected_head_height or 0.0))
        ),
        manual_override=manual,
        auto_entry_source=auto_source,
        auto_entry_scale=auto_scale,
    ).normalized()
    _ENTRY_META[id(entry)] = meta
    return meta


def set_entry_scale_manual(entry: Entry, scale: str | None) -> EntryClassification:
    current = get_entry_classification(entry)
    if scale in (None, "", "auto"):
        meta = EntryClassification(
            entry_source=current.auto_entry_source,
            entry_scale=current.auto_entry_scale,
            detected_head_height=current.detected_head_height,
            manual_override=False,
            auto_entry_source=current.auto_entry_source,
            auto_entry_scale=current.auto_entry_scale,
        )
    else:
        normalized_scale = str(scale)
        if normalized_scale not in ENTRY_SCALES:
            raise ValueError(f"unsupported entry scale: {scale}")
        meta = EntryClassification(
            entry_source=current.entry_source,
            entry_scale=normalized_scale,
            detected_head_height=current.detected_head_height,
            manual_override=True,
            auto_entry_source=current.auto_entry_source,
            auto_entry_scale=current.auto_entry_scale,
        )
    _ENTRY_META[id(entry)] = meta
    return meta


def classification_from_evidence(entry: Entry) -> EntryClassification:
    return infer_entry_classification(entry)


def register_layout_line_classification(line: Any, evidence: Entry) -> EntryClassification:
    incoming = classification_from_evidence(evidence)
    prior = _LINE_META.get(id(line))
    # Oversized evidence is structurally stronger for crop semantics than a
    # regular symbol/indent hit on the same physical row.
    if prior is None or incoming.entry_scale == "oversized" or prior.entry_source == "unknown":
        chosen = incoming
    else:
        chosen = prior
    _LINE_META[id(line)] = chosen.normalized()
    return _LINE_META[id(line)]


def get_layout_line_classification(line: Any) -> EntryClassification:
    return _LINE_META.get(id(line), EntryClassification(
        entry_source="indent",
        entry_scale="regular",
        auto_entry_source="indent",
        auto_entry_scale="regular",
    )).normalized()


def copy_layout_line_classification(line: Any, entry: Entry) -> EntryClassification:
    meta = get_layout_line_classification(line)
    return register_entry_classification(
        entry,
        entry_source=meta.entry_source,
        entry_scale=meta.entry_scale,
        detected_head_height=meta.detected_head_height,
        manual_override=False,
        auto_entry_source=meta.auto_entry_source,
        auto_entry_scale=meta.auto_entry_scale,
    )


def classified_entry_crop_height(
    entry: Entry,
    settings: AppSettings,
    *,
    regular_height: int | None = None,
    oversized_height: int | None = None,
) -> int:
    """Resolve one canonical OCR/review crop height from entry classification."""
    meta = get_entry_classification(entry)
    line_height = max(1, int(round(float(getattr(settings, "character_height", 1) or 1))))
    row_padding = max(0, int(round(float(getattr(settings, "row_padding", 0) or 0))))
    if regular_height is None or int(regular_height) <= 0:
        regular = max(1, line_height + row_padding)
    else:
        regular = max(1, int(regular_height))
    if meta.entry_scale != "oversized":
        return regular

    requested = max(0, int(oversized_height or 0))
    detected = int(round(meta.detected_head_height)) if meta.detected_head_height > 0 else 0
    if detected > 0:
        # Preserve the real observed display-head height, plus modest vertical
        # breathing room. Explicit project height may request a larger crop.
        return max(regular, requested, detected + 2 * row_padding)
    if requested > 0:
        return max(regular, requested)
    return max(regular, int(round(line_height * 2.5)))


def classification_sidecar_path(pdic_path: Path) -> Path:
    path = Path(pdic_path)
    parent = path.parent
    if parent.name.casefold() == "pdic" and parent.parent.name.casefold() == "data":
        return parent.parent / "EntryClassification" / f"{path.stem}.json"
    return parent / "QT" / "EntryClassification" / f"{path.stem}.json"


def _read_sidecar(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(raw, dict) or raw.get("format") != SIDECAR_FORMAT:
        return []
    rows = raw.get("entries")
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _distance(entry: Entry, row: dict[str, Any]) -> float:
    try:
        return abs(int(entry.x) - int(row.get("x", 0))) + abs(int(entry.y) - int(row.get("y", 0)))
    except (TypeError, ValueError):
        return 1e9


def _match_row(entry: Entry, rows: list[dict[str, Any]], used: set[int]) -> dict[str, Any] | None:
    candidates = [(idx, row, _distance(entry, row)) for idx, row in enumerate(rows) if idx not in used]
    if not candidates:
        return None
    exact = next(((idx, row) for idx, row, distance in candidates if distance == 0), None)
    if exact is not None:
        used.add(exact[0])
        return exact[1]
    idx, row, distance = min(candidates, key=lambda item: item[2])
    # A small Y move from separator refinement must not throw away a manual type.
    if distance <= 24:
        used.add(idx)
        return row
    return None


def _meta_from_row(row: dict[str, Any]) -> EntryClassification:
    return EntryClassification(
        entry_source=str(row.get("entry_source") or "unknown"),
        entry_scale=str(row.get("entry_scale") or "regular"),
        detected_head_height=float(row.get("detected_head_height") or 0.0),
        manual_override=bool(row.get("manual_override", False)),
        auto_entry_source=str(row.get("auto_entry_source") or row.get("entry_source") or "unknown"),
        auto_entry_scale=str(row.get("auto_entry_scale") or row.get("entry_scale") or "regular"),
    ).normalized()


def apply_classification_sidecar(entries: Iterable[Entry], pdic_path: Path) -> None:
    rows = _read_sidecar(classification_sidecar_path(pdic_path))
    used: set[int] = set()
    for entry in entries:
        row = _match_row(entry, rows, used)
        if row is None:
            get_entry_classification(entry)
            continue
        _ENTRY_META[id(entry)] = _meta_from_row(row)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def write_classification_sidecar(entries: Iterable[Entry], pdic_path: Path) -> None:
    path = classification_sidecar_path(pdic_path)
    old_rows = _read_sidecar(path)
    used: set[int] = set()
    output: list[dict[str, Any]] = []
    for entry in entries:
        meta = get_entry_classification(entry)
        old = _match_row(entry, old_rows, used)
        if old is not None:
            old_meta = _meta_from_row(old)
            if old_meta.manual_override and not meta.manual_override:
                meta = EntryClassification(
                    entry_source=meta.entry_source,
                    entry_scale=old_meta.entry_scale,
                    detected_head_height=max(meta.detected_head_height, old_meta.detected_head_height),
                    manual_override=True,
                    auto_entry_source=meta.auto_entry_source,
                    auto_entry_scale=meta.auto_entry_scale,
                ).normalized()
                _ENTRY_META[id(entry)] = meta
        row = {
            "x": int(entry.x),
            "y": int(entry.y),
            "word": str(entry.word or ""),
            **asdict(meta),
        }
        output.append(row)
    _atomic_json(path, {"format": SIDECAR_FORMAT, "entries": output})


def install_pdic_classification(formats_module: Any) -> None:
    """Wrap PDIC IO once so classification persists without changing PDIC."""
    if getattr(formats_module, "_entry_classification_installed", False):
        return
    original_read = formats_module.read_pdic
    original_write = formats_module.write_pdic

    def read_pdic(path: Path) -> list[Entry]:
        entries = original_read(path)
        apply_classification_sidecar(entries, Path(path))
        return entries

    def write_pdic(path: Path, entries: list[Entry], image_width: int, pages: tuple[str, str, str]) -> None:
        original_write(path, entries, image_width, pages)
        write_classification_sidecar(entries, Path(path))

    formats_module.read_pdic = read_pdic
    formats_module.write_pdic = write_pdic
    formats_module._entry_classification_installed = True


__all__ = [
    "EntryClassification",
    "ENTRY_SOURCES",
    "ENTRY_SCALES",
    "apply_classification_sidecar",
    "classification_sidecar_path",
    "classified_entry_crop_height",
    "copy_layout_line_classification",
    "get_entry_classification",
    "get_layout_line_classification",
    "install_pdic_classification",
    "register_entry_classification",
    "register_layout_line_classification",
    "set_entry_scale_manual",
    "write_classification_sidecar",
]
