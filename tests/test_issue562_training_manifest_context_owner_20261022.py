"""Issue #562: training v2 manifest and project-context have one physical owner."""
from __future__ import annotations

from dataclasses import asdict
import importlib
import json
from pathlib import Path
import subprocess
import sys

from picture_capture import training_export
from picture_capture.models import AppSettings
from picture_capture.persistence.project_storage import (
    settings_path, profile_path, replace_rules_path, headword_filter_rules_path,
)
from picture_capture.training import manifest_v2


def test_canonical_owner_and_historical_callable_format_identity() -> None:
    root = Path(training_export.__file__).resolve().parent
    assert Path(manifest_v2.__file__).resolve() == root / "training" / "manifest_v2.py"
    assert training_export.copy_project_context is manifest_v2.copy_project_context
    assert training_export.write_training_manifest is manifest_v2.write_training_manifest
    assert training_export.TRAINING_EXPORT_FORMAT == manifest_v2.TRAINING_EXPORT_FORMAT
    assert manifest_v2.TRAINING_EXPORT_FORMAT == "picture-capture-training-v2"
    facade = (root / "training_export.py").read_text(encoding="utf-8")
    assert "def copy_project_context(" not in facade
    assert "def write_training_manifest(" not in facade
    # v3 composition still composes the unchanged v2 function object.
    composed = importlib.import_module("picture_capture.training.export_composed")
    assert composed._write_training_manifest_v2 is manifest_v2.write_training_manifest


def test_context_snapshot_copies_exact_bytes_in_stable_order_without_mutating_sources(tmp_path) -> None:
    project = tmp_path / "原始项目"
    project.mkdir()
    staging = tmp_path / "staging"
    specs = [
        (settings_path(project), "picture_capture_settings.json", b'{"settings": true}'),
        (project / "wordslist.txt", "wordslist.txt", b"\xef\xbb\xbfentry\r\n"),
        (profile_path(project), "dictionary_profile.json", b'{"mode":"vertical"}'),
        # Replace rules deliberately missing; it must not be invented.
        (headword_filter_rules_path(project), "headword_filter_rules.txt", b"line1\r\nline2\n"),
    ]
    for source, _name, data in specs:
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(data)
    assert not replace_rules_path(project).is_file()
    copied = training_export.copy_project_context(project, staging)
    assert copied == [f"project_context/{name}" for _, name, _ in specs]
    for source, name, before in specs:
        assert source.read_bytes() == before
        assert (staging / "project_context" / name).read_bytes() == before
    assert not (staging / "project_context" / "_Replace.txt").exists()


def test_manifest_v2_exact_contract_counts_coordinates_and_serialized_settings(tmp_path) -> None:
    staging = tmp_path / "training"
    staging.mkdir()
    settings = AppSettings(dictionary_full_name="词典 G", ocr_resume_completed_pages=True)
    pages = [
        {"page": "a.tif", "ground_truth_count": 2, "annotation": "annotations/a.json"},
        {"page": "b.tif", "ground_truth_count": 3, "annotation": "annotations/b.json"},
    ]
    context = ["project_context/picture_capture_settings.json", "project_context/wordslist.txt"]
    result = training_export.write_training_manifest(
        staging,
        project_name="词典 G",
        settings=settings,
        pages=pages,
        context_files=context,
        software_version="test-build",
    )
    assert result == staging / "dataset_manifest.json"
    data = json.loads(result.read_text(encoding="utf-8"))
    assert data["format"] == "picture-capture-training-v2"
    assert data["software_version"] == "test-build"
    assert data["project_name"] == "词典 G"
    assert data["settings"] == asdict(settings)
    assert data["page_count"] == 2
    assert data["ground_truth_line_count"] == 5
    assert data["page_records"] == pages
    assert data["project_context_files"] == context
    annotations = data["annotation_contract"]
    assert "original-image pixels" in annotations["coordinates"]
    assert "original-image X/Y pixels" in annotations["layout_coordinates"]
    assert "saved .pdic" in annotations["ground_truth"]
    assert annotations["page_split_rule"].endswith("not adjacent pages")


def test_empty_context_and_pages_leave_valid_v2_manifest(tmp_path) -> None:
    staging = tmp_path / "snapshot"
    staging.mkdir()
    assert manifest_v2.copy_project_context(tmp_path / "missing-project", staging) == []
    target = manifest_v2.write_training_manifest(
        staging, project_name="empty", settings=AppSettings(), pages=[],
        context_files=[], software_version="0",
    )
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["page_count"] == payload["ground_truth_line_count"] == 0
    assert payload["project_context_files"] == payload["page_records"] == []


def test_leaf_first_import_does_not_load_training_export_or_gui() -> None:
    snippet = """
import importlib, sys
leaf = importlib.import_module("picture_capture.training.manifest_v2")
assert "picture_capture.training_export" not in sys.modules
assert "picture_capture.app" not in sys.modules
legacy = importlib.import_module("picture_capture.training_export")
assert legacy.write_training_manifest is leaf.write_training_manifest
assert legacy.copy_project_context is leaf.copy_project_context
assert legacy.TRAINING_EXPORT_FORMAT is leaf.TRAINING_EXPORT_FORMAT
"""
    run = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True, text=True, check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
