from __future__ import annotations

"""Supervised training-export extension with automatic/manual before-after data.

The historical exporter remains responsible for copying images, PDIC/PPP, OCR
traces and project context.  This extension enriches every page with:

* the exact automatic marker snapshot captured when available;
* otherwise a non-destructive ordinary-drawing recomputation, explicitly marked
  as recomputed rather than historical;
* the final human-corrected PDIC;
* one-to-one added/deleted/moved/unchanged correction records; and
* page-design diagnostics useful for explaining why a boundary was produced.

The resulting manifest records the exported page scope so a user can export a
small selected range and send only that reproducible experiment package.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable
import json
import math
import shutil

from PIL import Image

from . import formats
from .dictionary_page_design_refined import (
    detect_entries_from_page_design,
    layout_diagnostics,
)
from .layout_physical_indent import explicit_physical_layout_ops
from .image_utils import normalize_page_rgb
from .models import AppSettings, Entry
from .page_sections import read_page_sections
from .processing import column_index, derive_geometry, detect_entries
from .profile_semantics import effective_page_settings, page_template_analysis_image
from .training_baseline import load_automatic_baseline, baseline_path_for_pdic


TRAINING_EXPORT_FORMAT_V3 = "picture-capture-training-v3"


def _entry_rows(
    entries: list[Entry],
    geometry,
    *,
    label_source: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for order, entry in enumerate(entries, 1):
        column = (
            column_index(int(entry.x), geometry, int(entry.y))
            if getattr(geometry, "column_starts", None) else 0
        )
        rows.append({
            "order": order,
            "word": str(entry.word or ""),
            "source_x": int(entry.x),
            "source_y": int(entry.y),
            "x": int(entry.x),
            "y": int(entry.y),
            "column": int(column),
            "label_source": label_source,
            "confidence": (
                float(entry.confidence) if entry.confidence is not None else None
            ),
            "ocr_source": str(entry.ocr_source or ""),
            "issue_type": str(entry.issue_type or ""),
            "candidate_id": str(entry.candidate_id or ""),
        })
    return rows


def _captured_rows(payload: dict[str, Any], geometry) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for order, raw in enumerate(list(payload.get("entries") or []), 1):
        if not isinstance(raw, dict):
            continue
        try:
            x = int(raw.get("source_x"))
            y = int(raw.get("source_y"))
        except (TypeError, ValueError):
            continue
        column = (
            column_index(x, geometry, y)
            if getattr(geometry, "column_starts", None) else 0
        )
        row = dict(raw)
        row.update({
            "order": order,
            "source_x": x,
            "source_y": y,
            "x": x,
            "y": y,
            "column": int(column),
            "label_source": "captured_automatic_baseline",
        })
        rows.append(row)
    return rows


def _row_pair(auto: dict[str, Any], final: dict[str, Any]) -> dict[str, Any]:
    return {
        "automatic": auto,
        "final": final,
        "source_x_delta": int(final["source_x"]) - int(auto["source_x"]),
        "source_y_delta": int(final["source_y"]) - int(auto["source_y"]),
        "absolute_source_y_delta": abs(int(final["source_y"]) - int(auto["source_y"])),
    }


def compare_automatic_and_final(
    automatic: list[dict[str, Any]],
    final: list[dict[str, Any]],
    *,
    line_height: float,
) -> dict[str, Any]:
    """One-to-one correction diff in column/reading-axis space.

    X is recorded but not used to decide whether a semantic marker is the same
    line: automatic markers are drawn at the recovered column edge, while a
    manually added marker may use the nominal Profile edge.  Y/reading-axis
    movement is the meaningful edit.
    """
    match_tolerance = max(5, round(max(1.0, float(line_height)) * 0.58))
    unchanged_tolerance = max(2, round(max(1.0, float(line_height)) * 0.08))

    candidates: list[tuple[int, int, int]] = []
    for ai, auto in enumerate(automatic):
        for fi, truth in enumerate(final):
            if int(auto.get("column", -1)) != int(truth.get("column", -2)):
                continue
            delta = abs(int(auto["source_y"]) - int(truth["source_y"]))
            if delta <= match_tolerance:
                candidates.append((delta, ai, fi))
    candidates.sort()

    matched_auto: set[int] = set()
    matched_final: set[int] = set()
    unchanged: list[dict[str, Any]] = []
    moved: list[dict[str, Any]] = []
    for delta, ai, fi in candidates:
        if ai in matched_auto or fi in matched_final:
            continue
        matched_auto.add(ai)
        matched_final.add(fi)
        pair = _row_pair(automatic[ai], final[fi])
        if delta <= unchanged_tolerance:
            unchanged.append(pair)
        else:
            moved.append(pair)

    deleted = [row for index, row in enumerate(automatic) if index not in matched_auto]
    added = [row for index, row in enumerate(final) if index not in matched_final]
    return {
        "matching": {
            "same_column_required": True,
            "match_tolerance_px": int(match_tolerance),
            "unchanged_tolerance_px": int(unchanged_tolerance),
            "x_used_for_identity": False,
        },
        "summary": {
            "automatic_count": len(automatic),
            "final_count": len(final),
            "unchanged_count": len(unchanged),
            "moved_count": len(moved),
            "added_count": len(added),
            "deleted_count": len(deleted),
        },
        "added": added,
        "deleted": deleted,
        "moved": moved,
        "unchanged": unchanged,
    }


def _ordinary_recompute(
    page: Path,
    settings: AppSettings,
    page_index: int,
) -> tuple[list[Entry], Any]:
    ordinary = replace(settings)
    ordinary.detection_method = "left_edge"
    with Image.open(page) as opened:
        image = normalize_page_rgb(opened)
    return detect_entries(
        image,
        ordinary,
        profile_page_index=page_index,
        page_sections=read_page_sections(page),
    )


def _write_baseline_pdic(
    target: Path,
    rows: list[dict[str, Any]],
    image_width: int,
    page_name: str,
) -> None:
    entries = [
        Entry(
            word=str(row.get("word") or ""),
            x=int(row["source_x"]),
            y=int(row["source_y"]),
        )
        for row in rows
    ]
    writer = getattr(formats.write_pdic, "_original_write_pdic", formats.write_pdic)
    writer(target, entries, int(image_width), (page_name, "@", "@"))


def build_export_training_page(
    original_export_training_page: Callable[..., dict[str, Any]],
):
    """Wrap the v2 page exporter with exact/recomputed automatic supervision."""
    def export_training_page_v3(
        page: Path,
        project_root: Path,
        settings: AppSettings,
        staging_root: Path,
        page_index: int,
    ) -> dict[str, Any]:
        record = original_export_training_page(
            page, project_root, settings, staging_root, page_index,
        )
        staging_root = Path(staging_root)
        page = Path(page)
        annotation_path = staging_root / str(record["annotation"])
        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))

        with Image.open(page) as opened:
            image = normalize_page_rgb(opened)
            effective = effective_page_settings(settings, image.size, page_index)
            analysis = page_template_analysis_image(image, effective, page_index)
            geometry = derive_geometry(analysis, effective)
            image_width = image.width

        final_rows = list(annotation.get("ground_truth_lines") or [])
        captured = load_automatic_baseline(formats.pdic_path(page))
        baseline_provenance = "captured_at_automatic_draw"
        if captured:
            automatic_rows = _captured_rows(captured, geometry)
            baseline_captured_at = captured.get("captured_at_utc")
        else:
            baseline_provenance = "recomputed_at_export"
            baseline_captured_at = None
            automatic_entries, automatic_geometry = _ordinary_recompute(
                page, settings, page_index,
            )
            automatic_rows = _entry_rows(
                automatic_entries,
                automatic_geometry,
                label_source="recomputed_ordinary_baseline",
            )

        correction_diff = compare_automatic_and_final(
            automatic_rows,
            final_rows,
            line_height=float(effective.character_height),
        )

        artifacts_dir = staging_root / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        auto_json = artifacts_dir / f"{page.stem}_auto_baseline.json"
        auto_json.write_text(json.dumps({
            "format": "picture-capture-exported-auto-baseline-v1",
            "provenance": baseline_provenance,
            "captured_at_utc": baseline_captured_at,
            "page": page.name,
            "entries": automatic_rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        auto_pdic = artifacts_dir / f"{page.stem}_auto_baseline.pdic"
        _write_baseline_pdic(auto_pdic, automatic_rows, image_width, page.name)

        page_design = None
        try:
            with Image.open(page) as opened:
                result = detect_entries_from_page_design(
                    normalize_page_rgb(opened), settings,
                    page_index=page_index,
                    page_sections=read_page_sections(page),
                    ops=explicit_physical_layout_ops(),
                )
            page_design = layout_diagnostics(result.layout)
        except Exception as exc:
            page_design = {"available": False, "error": f"{type(exc).__name__}: {exc}"}

        annotation["format"] = TRAINING_EXPORT_FORMAT_V3
        annotation["automatic_baseline"] = {
            "provenance": baseline_provenance,
            "captured_at_utc": baseline_captured_at,
            "entry_count": len(automatic_rows),
            "entries": automatic_rows,
            "artifacts": {
                "json": auto_json.relative_to(staging_root).as_posix(),
                "pdic": auto_pdic.relative_to(staging_root).as_posix(),
                "historical_snapshot": (
                    baseline_path_for_pdic(formats.pdic_path(page)).name
                    if captured else None
                ),
            },
        }
        annotation["corrections"] = correction_diff
        annotation["page_design_diagnostics"] = page_design
        annotation_path.write_text(
            json.dumps(annotation, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        summary = correction_diff["summary"]
        record.update({
            "automatic_baseline_count": len(automatic_rows),
            "automatic_baseline_provenance": baseline_provenance,
            "added_count": int(summary["added_count"]),
            "deleted_count": int(summary["deleted_count"]),
            "moved_count": int(summary["moved_count"]),
            "unchanged_count": int(summary["unchanged_count"]),
        })
        return record

    return export_training_page_v3


def build_write_training_manifest(
    original_write_training_manifest: Callable[..., Path],
):
    def write_training_manifest_v3(
        staging_root: Path,
        *,
        project_name: str,
        settings: AppSettings,
        pages: list[dict[str, Any]],
        context_files: list[str],
        software_version: str,
    ) -> Path:
        path = original_write_training_manifest(
            staging_root,
            project_name=project_name,
            settings=settings,
            pages=pages,
            context_files=context_files,
            software_version=software_version,
        )
        manifest = json.loads(path.read_text(encoding="utf-8"))
        page_names = [str(record.get("page") or "") for record in pages]
        manifest["format"] = TRAINING_EXPORT_FORMAT_V3
        manifest["annotation_contract"].update({
            "automatic_baseline": (
                "exact snapshot captured when automatic drawing was written; "
                "historical pages without a snapshot are non-destructively recomputed at export"
            ),
            "corrections": (
                "one-to-one same-column automatic-to-final comparison with explicit "
                "added/deleted/moved/unchanged records"
            ),
            "baseline_provenance": (
                "captured_at_automatic_draw is historical ground truth for the program output; "
                "recomputed_at_export is reproducible but may differ if settings/software changed"
            ),
        })
        manifest["export_scope"] = {
            "selection": "pages supplied by the current export scope",
            "first_page": page_names[0] if page_names else None,
            "last_page": page_names[-1] if page_names else None,
            "page_names": page_names,
            "page_count": len(page_names),
        }
        manifest["correction_summary"] = {
            "automatic_line_count": sum(int(p.get("automatic_baseline_count", 0)) for p in pages),
            "final_line_count": sum(int(p.get("ground_truth_count", 0)) for p in pages),
            "added_count": sum(int(p.get("added_count", 0)) for p in pages),
            "deleted_count": sum(int(p.get("deleted_count", 0)) for p in pages),
            "moved_count": sum(int(p.get("moved_count", 0)) for p in pages),
            "unchanged_count": sum(int(p.get("unchanged_count", 0)) for p in pages),
            "captured_baseline_pages": sum(
                p.get("automatic_baseline_provenance") == "captured_at_automatic_draw"
                for p in pages
            ),
            "recomputed_baseline_pages": sum(
                p.get("automatic_baseline_provenance") == "recomputed_at_export"
                for p in pages
            ),
        }
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    return write_training_manifest_v3


def select_page_range(
    pages: list[Path],
    first_page: str | None = None,
    last_page: str | None = None,
) -> list[Path]:
    """Resolve an inclusive page-name range for UI/CLI training export callers."""
    if not pages:
        return []
    ordered = list(pages)
    names = [page.name for page in ordered]

    def resolve(value: str | None, default: int) -> int:
        text = str(value or "").strip()
        if not text:
            return default
        for index, page in enumerate(ordered):
            if text in {page.name, page.stem}:
                return index
        # Numeric page identifiers can be entered without leading zeroes.
        try:
            number = int(text)
        except ValueError:
            return default
        for index, page in enumerate(ordered):
            digits = "".join(ch for ch in page.stem if ch.isdigit())
            if digits and int(digits) == number:
                return index
        return default

    start = resolve(first_page, 0)
    end = resolve(last_page, len(ordered) - 1)
    if start > end:
        start, end = end, start
    return ordered[start:end + 1]
