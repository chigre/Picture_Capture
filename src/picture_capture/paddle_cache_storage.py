from __future__ import annotations

"""Implementation helpers for compact Paddle OCR cache persistence.

Historical public/core names remain defined in paddle_headwords_core.
Dependencies that participate in the public monkeypatch contract are supplied
explicitly by those core wrappers at call time.
"""

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable


def atomic_write_text_impl(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding=encoding,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def atomic_write_json_impl(
    path: Path,
    payload: dict[str, Any],
    *,
    write_text: Callable[..., None],
) -> None:
    write_text(
        path,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def compact_cached_candidate_impl(
    row: Any,
    *,
    source_only: Callable[[Any], Any],
) -> Any:
    if not isinstance(row, dict):
        return row
    if "meta" in row:
        return {"meta": source_only(row.get("meta") or {})}
    compact: dict[str, Any] = {}
    for key in ("box", "accepted", "reject_reason"):
        if key in row:
            compact[key] = source_only(row[key])
    features = row.get("features")
    if isinstance(features, dict):
        kept_features = {
            key: features[key]
            for key in (
                "visual_marker_template_score",
                "ordinary_strong_edge_visual_rescue",
            )
            if key in features
        }
        if kept_features:
            compact["features"] = kept_features
    return compact


def compact_ocr_cache_payload_impl(
    payload: dict[str, Any],
    *,
    source_only: Callable[[Any], Any],
    compact_candidate: Callable[[Any], Any],
) -> dict[str, Any]:
    result = dict(payload)
    compact_columns: list[dict[str, Any]] = []
    for raw in list(payload.get("columns") or []):
        if not isinstance(raw, dict):
            continue
        column: dict[str, Any] = {}
        for key in ("column", "band_size", "ocr_records", "paddle_accepted_count"):
            if key in raw:
                column[key] = source_only(raw[key])
        candidates = [
            compact_candidate(item)
            for item in list(raw.get("candidates") or [])
        ]
        if candidates:
            column["candidates"] = candidates
        compact_columns.append(column)
    result["columns"] = compact_columns
    result["cache_storage"] = "compact-v1"
    return source_only(result)


def regenerable_sidecars_impl(
    cache_path: Path,
    *,
    suffixes: tuple[str, ...],
) -> list[Path]:
    return [
        cache_path.with_name(f"{cache_path.stem}{suffix}")
        for suffix in suffixes
    ]


def compact_ocr_cache_file_impl(
    cache_path: Path,
    *,
    sidecar_paths: Callable[[Path], list[Path]],
    compact_payload: Callable[[dict[str, Any]], dict[str, Any]],
    write_json: Callable[[Path, dict[str, Any]], None],
) -> tuple[int, int, int]:
    cache_path = Path(cache_path)
    before_bytes = 0
    if cache_path.exists():
        try:
            before_bytes += int(cache_path.stat().st_size)
        except OSError:
            pass
    sidecars = sidecar_paths(cache_path)
    for path in sidecars:
        if path.exists():
            try:
                before_bytes += int(path.stat().st_size)
            except OSError:
                pass

    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"OCR cache is not a JSON object: {cache_path.name}")
        write_json(cache_path, compact_payload(payload))

    removed = 0
    for path in sidecars:
        if not path.exists():
            continue
        path.unlink()
        removed += 1

    after_bytes = 0
    if cache_path.exists():
        try:
            after_bytes += int(cache_path.stat().st_size)
        except OSError:
            pass
    return before_bytes, after_bytes, removed
