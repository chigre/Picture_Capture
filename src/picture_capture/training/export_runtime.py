from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import shutil

from PIL import Image, ImageOps

from ..io.formats import pdic_path, read_pdic, read_ppp
from ..preprocess.analysis_image import normalize_page_rgb
from ..models import AppSettings
from ..geometry.coordinate_space import SOURCE_COORDINATE_SPACE, coordinate_contract
from ..processing import column_index, derive_geometry
from ..profile.semantics import (
    effective_page_settings,
    excluded_source_side,
    excluded_source_side_percent,
    page_template_analysis_image,
)
from ..persistence.project_storage import ocr_cache_root, ppp_read_path_for_image


from ..training.manifest_v2 import (
    TRAINING_EXPORT_FORMAT, copy_project_context, write_training_manifest,
)
from ..training.zip_publish import TrainingExportCancelled, make_training_zip
from ..training import export_page_v2 as _page_v2


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
from ..training.ground_truth_matching import _candidate_ground_truth_link

def export_training_page(
    page: Path,
    project_root: Path,
    settings: AppSettings,
    staging_root: Path,
    page_index: int,
) -> dict[str, Any]:
    """Historical training-export API; canonical staging lives in training/."""
    return _page_v2.export_training_page(
        page, project_root, settings, staging_root, page_index, deps={
            "shutil": shutil,
            "Image": Image,
            "normalize_page_rgb": normalize_page_rgb,
            "effective_page_settings": effective_page_settings,
            "page_template_analysis_image": page_template_analysis_image,
            "derive_geometry": derive_geometry,
            "pdic_path": pdic_path,
            "read_pdic": read_pdic,
            "column_index": column_index,
            "SOURCE_COORDINATE_SPACE": SOURCE_COORDINATE_SPACE,
            "ppp_read_path_for_image": ppp_read_path_for_image,
            "read_ppp": read_ppp,
            "ocr_cache_root": ocr_cache_root,
            "_read_json": _read_json,
            "_candidate_ground_truth_link": _candidate_ground_truth_link,
            "excluded_source_side": excluded_source_side,
            "excluded_source_side_percent": excluded_source_side_percent,
            "coordinate_contract": coordinate_contract,
            "TRAINING_EXPORT_FORMAT": TRAINING_EXPORT_FORMAT,
            "json": json,
        },
    )

# Public compatibility: original module path remains the *same module object*
# under picture_capture.training_export; keep locally-defined helper pickles.
for _historical_training_name in ("_read_json", "_copy_if_exists", "export_training_page"):
    globals()[_historical_training_name].__module__ = "picture_capture.training_export"
del _historical_training_name
