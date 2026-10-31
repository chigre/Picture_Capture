"""Round 23: large processing-core extraction ownership and live facade checks."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from picture_capture import processing_core as core
from picture_capture.models import AppSettings, Entry
from picture_capture.quality import detection_entry_fusion
from picture_capture.geometry import column_path_tracking
from picture_capture.ocr import ordinary_marker_text_enrichment


def test_round23_owners_and_exact_function_boundaries():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(root.glob("*.py"))) == 5
    owners = {
        "quality/detection_entry_fusion.py": {"fuse_detection_entries"},
        "geometry/column_path_tracking.py": {"estimate_column_paths"},
        "ocr/ordinary_marker_text_enrichment.py": {
            "ocr_existing_entry_words_from_markers_impl",
        },
    }
    for relative, funcs in owners.items():
        path = root / relative
        assert path.exists()
        assert not (root / path.name).exists()
        nodes = ast.parse(path.read_text(encoding="utf-8")).body
        assert {n.name for n in nodes if isinstance(n, ast.FunctionDef)} == funcs
        # Historical persisted models must never move into algorithm leaves.
        assert not any(isinstance(n, ast.ClassDef) for n in nodes)
        assert not any(isinstance(n, (ast.Assign, ast.AnnAssign)) for n in nodes)


def test_entry_fusion_retains_old_signature_identity_and_public_hook(monkeypatch):
    assert core._fuse_detection_entries.__module__ == "picture_capture.processing_core"
    assert list(inspect.signature(core._fuse_detection_entries).parameters) == [
        "ordinary_entries", "ocr_entries", "geometry", "settings",
        "page_sections", "review_candidates", "image",
    ]
    seen = {}
    def spy(ordinary, ocr, geometry, settings, sections=None, review=None, image=None, *, deps):
        seen.update(deps)
        return ordinary + ocr

    monkeypatch.setattr(detection_entry_fusion, "fuse_detection_entries", spy)
    sorted_hook = lambda *args: []
    monkeypatch.setattr(core, "sort_entries_reading_order", sorted_hook)
    first = Entry(word="", x=10, y=20)
    second = Entry(word="词", x=10, y=21)
    got = core._fuse_detection_entries([first], [second], object(), AppSettings())
    assert got == [first, second]
    assert seen["sort_entries_reading_order"] is sorted_hook
    assert seen["_entry_with_fused_metadata"] is core._entry_with_fused_metadata
    assert seen["_prefer_ocr_separator_position"] is core._prefer_ocr_separator_position


def test_entry_fusion_unpaired_sort_behavior_and_original_objects():
    settings = AppSettings(columns=1, manual_x=15, column_width=60,
                           start_y=0, follow_column_deformation=False)
    geometry = core.derive_nominal_geometry(110, 110, settings)
    one = Entry(word="", x=15, y=20)
    two = Entry(word="OCR", x=15, y=80)
    assert core._fuse_detection_entries([one], [], geometry, settings) == [one]
    assert core._fuse_detection_entries([], [two], geometry, settings) == [two]
    assert core._fuse_detection_entries([], [], geometry, settings) == []


def test_column_tracking_exact_flat_mode_and_current_callbacks(monkeypatch):
    settings = AppSettings()
    settings.follow_column_deformation = False
    analysis = Image.new("RGB", (100, 100), "white")
    paths = core._estimate_column_paths(
        analysis, 2.0, [12, 70], [45, 20], 20, 80, settings, 1.0,
    )
    assert len(paths) == 2
    assert all(type(p) is core.ColumnPath for p in paths)
    assert paths[0].points == [(10, 6), (40, 6)]
    assert paths[1].points == [(10, 35), (40, 35)]
    assert core._estimate_column_paths.__module__ == "picture_capture.processing_core"
    assert list(inspect.signature(core._estimate_column_paths).parameters) == [
        "analysis", "scale", "starts_analysis", "widths_analysis",
        "top_analysis", "bottom_analysis", "settings", "geometry_to_analysis",
    ]

    seen = {}
    def spy(*args, deps):
        seen.update(deps)
        return []
    monkeypatch.setattr(column_path_tracking, "estimate_column_paths", spy)
    fake_smooth = lambda *args, **kwargs: [2]
    monkeypatch.setattr(core, "_smooth_track", fake_smooth)
    assert core._estimate_column_paths(
        analysis, 1.0, [], [], 0, 90, settings, 1.0,
    ) == []
    assert seen["_smooth_track"] is fake_smooth
    assert seen["ColumnPath"] is core.ColumnPath
    assert seen["np"] is np


def test_existing_marker_ocr_old_signature_and_runtime_hooks(monkeypatch):
    assert core.ocr_existing_entry_words_from_markers.__module__ == "picture_capture.processing_core"
    assert list(inspect.signature(core.ocr_existing_entry_words_from_markers).parameters) == [
        "image", "entries", "settings", "replace_rules", "profile_page_index",
        "page_sections", "profile_path", "only_blank",
    ]
    seen = {}
    def spy(image, entries, settings, replace_rules, *, deps, **kwargs):
        seen.update(deps)
        assert kwargs["only_blank"] is False
        return entries, {"total": len(entries)}
    monkeypatch.setattr(
        ordinary_marker_text_enrichment,
        "ocr_existing_entry_words_from_markers_impl", spy,
    )
    crop_spy = lambda *args, **kwargs: ("crop", False)
    monkeypatch.setattr(core, "_ordinary_marker_local_crop", crop_spy)
    image = Image.new("RGB", (40, 50), "white")
    entry = Entry(word="", x=10, y=10)
    got, stats = core.ocr_existing_entry_words_from_markers(
        image, [entry], AppSettings(), [], only_blank=False,
    )
    assert got == [entry] and stats == {"total": 1}
    assert seen["_ordinary_marker_local_crop"] is crop_spy
    assert seen["sort_entries_reading_order"] is core.sort_entries_reading_order
    assert seen["process_ocr_text"] is core.process_ocr_text
