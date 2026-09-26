from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable
import json
import shutil
import uuid
import zipfile

from PIL import Image, ImageOps

from .formats import pdic_path, read_pdic, read_ppp
from .image_utils import normalize_page_rgb
from .models import AppSettings
from .coordinate_space import (
    SOURCE_COORDINATE_SPACE,
    coordinate_contract,
    setting_pixels,
)
from .processing import column_index, derive_geometry
from .profile_semantics import (
    effective_page_settings,
    excluded_source_side,
    excluded_source_side_percent,
    page_template_analysis_image,
)
from .project_storage import (
    headword_filter_rules_path, ocr_cache_root, ppp_read_path_for_image,
    profile_path, replace_rules_path, settings_path,
)


TRAINING_EXPORT_FORMAT = "picture-capture-training-v2"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _copy_if_exists(source: Path, target: Path) -> str | None:
    if not source.exists() or not source.is_file():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target.as_posix()


def _candidate_ground_truth_link(
    candidate: dict[str, Any],
    ground_truth: list[dict[str, Any]],
    geometry,
    line_height: int,
) -> dict[str, Any]:
    """Link one OCR candidate to the nearest saved line on canonical reading V.

    Ground-truth points remain original-image pixels. Reading-order distance is
    measured in full-resolution canonical V so rotated/vertical dictionaries do
    not accidentally compare physical source Y.
    """
    try:
        column = int(candidate.get("column", -1))
    except Exception:
        return {
            "ground_truth_selected": False,
            "nearest_ground_truth_source": None,
            "ground_truth_canonical_v_delta": None,
        }

    candidate_v = candidate.get("canonical_v")
    if candidate_v is None:
        try:
            source_x = int(candidate.get("source_x"))
            source_y = int(
                candidate.get(
                    "source_y",
                    candidate.get("refined_source_y"),
                )
            )
            _u, candidate_v = geometry.source_to_canonical(source_x, source_y)
        except Exception:
            return {
                "ground_truth_selected": False,
                "nearest_ground_truth_source": None,
                "ground_truth_canonical_v_delta": None,
            }
    candidate_v = int(candidate_v)

    same_col = [
        row for row in ground_truth
        if int(row.get("column", -2)) == column
    ]
    if not same_col:
        return {
            "ground_truth_selected": False,
            "nearest_ground_truth_source": None,
            "ground_truth_canonical_v_delta": None,
        }

    def row_v(row: dict[str, Any]) -> int:
        _u, v = geometry.source_to_canonical(
            int(row["x"]), int(row["y"])
        )
        return int(v)

    nearest = min(same_col, key=lambda row: abs(row_v(row) - candidate_v))
    nearest_v = row_v(nearest)
    delta = abs(nearest_v - candidate_v)
    tolerance = max(4, round(max(1, line_height) * 0.60))
    return {
        "ground_truth_selected": bool(delta <= tolerance),
        "nearest_ground_truth_source": [
            int(nearest["x"]), int(nearest["y"])
        ],
        "nearest_ground_truth_canonical_v": int(nearest_v),
        "ground_truth_canonical_v_delta": int(delta),
        # Compatibility fields remain source-space facts where possible.
        "nearest_ground_truth_y": int(nearest["y"]),
        "ground_truth_y_delta": (
            abs(int(nearest["y"]) - int(candidate.get("source_y", nearest["y"])))
            if candidate.get("source_y") is not None else None
        ),
    }

def export_training_page(
    page: Path,
    project_root: Path,
    settings: AppSettings,
    staging_root: Path,
    page_index: int,
) -> dict[str, Any]:
    """Export one annotated page into a training-package staging directory."""
    page = Path(page)
    project_root = Path(project_root)
    staging_root = Path(staging_root)

    images_dir = staging_root / "images"
    annotations_dir = staging_root / "annotations"
    artifacts_dir = staging_root / "artifacts"
    ocr_dir = staging_root / "ocr"
    images_dir.mkdir(parents=True, exist_ok=True)
    annotations_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    ocr_dir.mkdir(parents=True, exist_ok=True)

    image_target = images_dir / page.name
    shutil.copy2(page, image_target)

    with Image.open(page) as opened:
        image = normalize_page_rgb(opened)
        width, height = image.size
        # Export the exact same per-page layout geometry used by detection and
        # the main canvas. Physical Profile percentages are resolved once at
        # this boundary; only the disposable analysis image is masked.
        effective = effective_page_settings(settings, image.size, page_index)
        analysis_image = page_template_analysis_image(image, effective, page_index)
        geometry = derive_geometry(analysis_image, effective)

    pdic = pdic_path(page)
    entries = read_pdic(pdic)
    ground_truth: list[dict[str, Any]] = []
    for order, entry in enumerate(entries, 1):
        col = column_index(int(entry.x), geometry, int(entry.y)) if geometry.column_starts else 0
        ground_truth.append({
            "order": order,
            "word": entry.word,
            "coordinate_space": SOURCE_COORDINATE_SPACE,
            "source_x": int(entry.x),
            "source_y": int(entry.y),
            # Compatibility aliases for v1 consumers. The coordinate_space field
            # makes their meaning explicit; new consumers should use source_x/y.
            "x": int(entry.x),
            "y": int(entry.y),
            "column": int(col),
            "label_source": "saved_pdic",
        })

    pdic_rel = None
    if pdic.exists():
        target = artifacts_dir / pdic.name
        shutil.copy2(pdic, target)
        pdic_rel = target.relative_to(staging_root).as_posix()

    ppp = ppp_read_path_for_image(page)
    polygons = read_ppp(ppp) if ppp.exists() else []
    ppp_rel = None
    if ppp.exists():
        target = artifacts_dir / ppp.name
        shutil.copy2(ppp, target)
        ppp_rel = target.relative_to(staging_root).as_posix()

    cache_source = ocr_cache_root(project_root) / f"{page.stem}.json"
    cache = _read_json(cache_source) if cache_source.exists() else {}
    ocr_files: list[str] = []
    ocr_names = [
        f"{page.stem}.json",
        f"{page.stem}_manual_selection.json",
        f"{page.stem}_ocr_diagnostics.txt",
        f"{page.stem}_ocr_comparison.txt",
        f"{page.stem}_issues.tsv",
        f"{page.stem}_ocr_engines.tsv",
        f"{page.stem}_fusion.tsv",
    ]
    ocr_source_dir = ocr_cache_root(project_root)
    for name in ocr_names:
        source = ocr_source_dir / name
        if source.exists():
            target = ocr_dir / name
            shutil.copy2(source, target)
            ocr_files.append(target.relative_to(staging_root).as_posix())

    manual_selection = _read_json(
        ocr_source_dir / f"{page.stem}_manual_selection.json"
    )
    canonical_width, canonical_height = geometry.transform.canonical_size(
        image.size
    )
    canonical_line_height = setting_pixels(
        effective.character_height, canonical_width, effective,
    )
    candidates: list[dict[str, Any]] = []
    for raw in list(cache.get("review_candidates") or []):
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        row.update(
            _candidate_ground_truth_link(
                row, ground_truth, geometry, canonical_line_height,
            )
        )
        candidates.append(row)

    header_boundary_y = None
    if str(getattr(settings, "profile_header_mode", "auto") or "auto") == "present":
        header_boundary_y = round(
            height
            * float(getattr(settings, "profile_header_percent", 0.0) or 0.0)
            / 100.0
        )
    footer_boundary_y = None
    if str(getattr(settings, "profile_footer_mode", "auto") or "auto") == "present":
        footer_boundary_y = round(
            height
            * (
                1.0
                - float(getattr(settings, "profile_footer_percent", 0.0) or 0.0)
                / 100.0
            )
        )
    side = excluded_source_side(settings, page_index)
    side_percent = (
        excluded_source_side_percent(settings, page_index)
        if side is not None else 0.0
    )
    side_boundary_x = None
    if side == "left":
        side_boundary_x = round(width * side_percent / 100.0)
    elif side == "right":
        side_boundary_x = round(width * (1.0 - side_percent / 100.0))

    source_column_paths = []
    for path in geometry.column_paths:
        source_column_paths.append([
            list(geometry.canonical_to_source(int(u), int(v)))
            for v, u in path.points
        ])

    annotation = {
        "format": TRAINING_EXPORT_FORMAT,
        "page_index": int(page_index),
        "page": page.name,
        "image": {
            "file": image_target.relative_to(staging_root).as_posix(),
            "width": int(width),
            "height": int(height),
            "mode": "RGB",
        },
        "annotation_status": "human_verified_saved_pdic",
        "ground_truth_lines": ground_truth,
        "illustration_polygons": [
            {
                "label": region.label,
                "coordinate_space": SOURCE_COORDINATE_SPACE,
                "source_points_xy": [[int(x), int(y)] for x, y in region.points],
                # Compatibility alias; source_points_xy is the preferred v2 key.
                "points": [[int(x), int(y)] for x, y in region.points],
            }
            for region in polygons
        ],
        "coordinate_contract": coordinate_contract(),
        "page_template": {
            "coordinate_space": SOURCE_COORDINATE_SPACE,
            "header_mode": str(getattr(settings, "profile_header_mode", "auto")),
            "header_percent": float(getattr(settings, "profile_header_percent", 0.0) or 0.0),
            "header_boundary_y": header_boundary_y,
            "footer_mode": str(getattr(settings, "profile_footer_mode", "auto")),
            "footer_percent": float(getattr(settings, "profile_footer_percent", 0.0) or 0.0),
            "footer_boundary_y": footer_boundary_y,
            "excluded_side": side,
            "side_percent": float(side_percent),
            "side_boundary_x": side_boundary_x,
        },
        "layout": {
            "coordinate_space": SOURCE_COORDINATE_SPACE,
            "transform_used_internally": geometry.transform.kind,
            "columns": int(len(geometry.column_starts)),
            "source_column_paths_xy": source_column_paths,
            "line_height_px": int(canonical_line_height),
            "row_padding_px": int(
                setting_pixels(
                    effective.row_padding, canonical_width, effective,
                )
            ),
        },
        "artifacts": {
            "pdic": pdic_rel,
            "ppp": ppp_rel,
        },
        "ocr_trace": {
            "cache_available": bool(cache),
            "ocr_files": ocr_files,
            "manual_override_count": int(cache.get("manual_override_count") or 0),
            "page_quality": cache.get("page_quality") or {},
            "manual_selection": manual_selection,
            "candidates": candidates,
        },
    }

    annotation_path = annotations_dir / f"{page.stem}.json"
    annotation_path.write_text(json.dumps(annotation, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "page": page.name,
        "annotation": annotation_path.relative_to(staging_root).as_posix(),
        "image": image_target.relative_to(staging_root).as_posix(),
        "ground_truth_count": len(ground_truth),
        "polygon_count": len(polygons),
        "ocr_candidate_count": len(candidates),
        "ocr_cache_available": bool(cache),
    }


def copy_project_context(project_root: Path, staging_root: Path) -> list[str]:
    """Copy compact project-level context useful for reproducible training."""
    project_root = Path(project_root)
    staging_root = Path(staging_root)
    target_root = staging_root / "project_context"
    copied: list[str] = []
    sources = [
        (settings_path(project_root), "picture_capture_settings.json"),
        (project_root / "wordslist.txt", "wordslist.txt"),
        (profile_path(project_root), "dictionary_profile.json"),
        (replace_rules_path(project_root), "_Replace.txt"),
        (headword_filter_rules_path(project_root), "headword_filter_rules.txt"),
    ]
    for source, name in sources:
        if source.exists() and source.is_file():
            target = target_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target.relative_to(staging_root).as_posix())
    return copied


def write_training_manifest(
    staging_root: Path,
    *,
    project_name: str,
    settings: AppSettings,
    pages: list[dict[str, Any]],
    context_files: list[str],
    software_version: str,
) -> Path:
    exported_settings = asdict(settings)
    if int(exported_settings.get("geometry_coordinate_version", 0) or 0) >= 3:
        exported_settings.pop("geometry_reference_width", None)
        exported_settings.pop("parameter_display_width", None)
    manifest = {
        "format": TRAINING_EXPORT_FORMAT,
        "software_version": software_version,
        "project_name": project_name,
        "annotation_contract": {
            "ground_truth": "saved .pdic lines confirmed by the user at export time",
            "negative_candidates": "OCR review candidates not matched to a saved ground-truth line",
            "coordinates": "ground truth, illustration polygons and page-template boundaries use original-image pixels",
            "layout_coordinates": "exported layout geometry uses original-image X/Y pixels",
            "persisted_geometry": "settings geometry uses original-image pixels directly; no reference-width scaling",
            "page_split_rule": "future train/validation/test splits should be performed by dictionary, not adjacent pages",
        },
        "settings": exported_settings,
        "page_count": len(pages),
        "ground_truth_line_count": sum(int(p.get("ground_truth_count", 0)) for p in pages),
        "page_records": pages,
        "project_context_files": context_files,
    }
    path = Path(staging_root) / "dataset_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class TrainingExportCancelled(RuntimeError):
    """Raised when a training-package build is cooperatively stopped."""


def make_training_zip(
    staging_root: Path,
    zip_path: Path,
    *,
    should_stop: Callable[[], bool] | None = None,
) -> Path:
    """Create the training ZIP off to the side and publish it only when complete."""
    staging_root = Path(staging_root)
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    temp_zip = zip_path.with_name(f".{zip_path.name}.{uuid.uuid4().hex}.tmp")

    def check_stop() -> None:
        if should_stop is not None and should_stop():
            raise TrainingExportCancelled("训练标记包导出已停止")

    try:
        temp_zip.unlink(missing_ok=True)
        paths = sorted(staging_root.rglob("*"), key=lambda p: p.as_posix().casefold())
        check_stop()
        with zipfile.ZipFile(
            temp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
        ) as zf:
            for path in paths:
                check_stop()
                if path.is_file():
                    zf.write(path, arcname=path.relative_to(staging_root).as_posix())
        check_stop()
        temp_zip.replace(zip_path)
    except Exception:
        temp_zip.unlink(missing_ok=True)
        raise
    return zip_path
