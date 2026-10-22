from __future__ import annotations

"""Training v2 project-context snapshot and manifest serialization owners.

Training/export_composed still composes the v2 manifest with v3 fields.
Legacy training_export re-exports identical functions and format string.
No GUI, OCR, layout or archive publishing is owned here.
"""

from dataclasses import asdict
from pathlib import Path
from typing import Any
import json
import shutil

from ..models import AppSettings
from ..persistence.project_storage import (
    settings_path, profile_path, replace_rules_path,
    headword_filter_rules_path,
)

TRAINING_EXPORT_FORMAT = "picture-capture-training-v2"


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
