from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import shutil

from PIL import Image, ImageOps

from .io.formats import pdic_path, read_pdic, read_ppp
from .image_utils import normalize_page_rgb
from .models import AppSettings
from .geometry.coordinate_space import SOURCE_COORDINATE_SPACE, coordinate_contract
from .processing import column_index, derive_geometry
from .profile.semantics import (
    effective_page_settings,
    excluded_source_side,
    excluded_source_side_percent,
    page_template_analysis_image,
)
from .project_storage import ocr_cache_root, ppp_read_path_for_image


from .training.manifest_v2 import (
    TRAINING_EXPORT_FORMAT, copy_project_context, write_training_manifest,
)
from .training.zip_publish import TrainingExportCancelled, make_training_zip


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


# Keep the training_export compatibility and monkeypatch import path stable;
# source-pixel matching itself is owned by training/ground_truth_matching.
from .training.ground_truth_matching import _candidate_ground_truth_link

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
    canonical_line_height = int(effective.character_height)
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
            "row_padding_px": int(effective.row_padding),
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


