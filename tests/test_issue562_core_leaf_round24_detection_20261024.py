"""Round 24: actual detection, refinement and OCR algorithm owners preserve core façade."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from PIL import Image

from picture_capture import processing_core as core
from picture_capture.models import AppSettings, Entry
from picture_capture.detection import page_method_dispatch
from picture_capture.refinement import existing_entry_positions
from picture_capture.ocr import legacy_entry_text_reading


def test_algorithm_leaf_scope_and_historical_ownership():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(root.glob("*.py"))) == 7
    owners = {
        "detection/page_method_dispatch.py": {"detect_entries_impl"},
        "refinement/existing_entry_positions.py": {"refine_existing_entries_with_geometry_impl"},
        "ocr/legacy_entry_text_reading.py": {"ocr_entries_impl"},
    }
    for relative, expected in owners.items():
        path = root / relative
        assert path.is_file()
        assert not (root / path.name).exists()
        nodes = ast.parse(path.read_text(encoding="utf-8")).body
        assert {n.name for n in nodes if isinstance(n, ast.FunctionDef)} == expected
        assert not any(isinstance(n, (ast.Assign, ast.AnnAssign, ast.ClassDef)) for n in nodes)
    assert core.detect_entries.__module__ == "picture_capture.processing_core"
    assert core._refine_existing_entries_with_geometry.__module__ == "picture_capture.processing_core"
    assert core.ocr_entries.__module__ == "picture_capture.processing_core"
    assert list(inspect.signature(core.detect_entries).parameters) == [
        "image", "settings", "paddle_cache_path", "force_paddle_refresh",
        "paddle_filter_rules_path", "profile_page_index", "page_sections",
        "left_edge_detector",
    ]
    assert list(inspect.signature(core._refine_existing_entries_with_geometry).parameters) == [
        "entries", "effective", "analysis_source", "geometry",
        "align_to_ink_top", "fixed_half_gutter",
    ]
    assert list(inspect.signature(core.ocr_entries).parameters) == [
        "image", "entries", "settings", "replace_rules",
        "profile_page_index", "page_sections",
    ]


def test_detect_dispatch_preserves_live_core_fusion_and_ordinary_hooks(monkeypatch):
    seen = {}
    def delegate(*args, deps, **kwargs):
        seen.update(deps)
        return ["sentinel"], "geometry"
    monkeypatch.setattr(page_method_dispatch, "detect_entries_impl", delegate)
    fake_fuse = lambda *args, **kwargs: []
    fake_ordinary = lambda *args, **kwargs: ([], None)
    monkeypatch.setattr(core, "_fuse_detection_entries", fake_fuse)
    monkeypatch.setattr(core, "_detect_entries_left_edge", fake_ordinary)
    image = Image.new("RGB", (80, 60), "white")
    got = core.detect_entries(image, AppSettings())
    assert got == (["sentinel"], "geometry")
    assert seen["_fuse_detection_entries"] is fake_fuse
    assert seen["_detect_entries_left_edge"] is fake_ordinary
    assert seen["sort_entries_reading_order"] is core.sort_entries_reading_order


def test_refinement_preserves_live_replace_and_column_index(monkeypatch):
    seen = {}
    def delegate(*args, deps, **kwargs):
        seen.update(deps)
        return args[0], {"moved": 0}
    monkeypatch.setattr(
        existing_entry_positions, "refine_existing_entries_with_geometry_impl", delegate,
    )
    live_column_index = lambda *args, **kwargs: 0
    monkeypatch.setattr(core, "column_index", live_column_index)
    entry = Entry(word="", x=3, y=4)
    entries, stats = core._refine_existing_entries_with_geometry(
        [entry], AppSettings(), Image.new("RGB", (24, 20)), object(),
        align_to_ink_top=True,
    )
    assert entries == [entry] and stats == {"moved": 0}
    assert seen["column_index"] is live_column_index
    assert seen["replace"] is core.replace
    assert seen["np"] is core.np


def test_legacy_ocr_entrypoint_passes_current_text_and_crop_hooks(monkeypatch):
    seen = {}
    def delegate(*args, deps, **kwargs):
        seen.update(deps)
        return ["ocr-value"]
    monkeypatch.setattr(legacy_entry_text_reading, "ocr_entries_impl", delegate)
    live_run = lambda *args, **kwargs: "raw"
    monkeypatch.setattr(core, "run_tesseract", live_run)
    words = core.ocr_entries(
        Image.new("RGB", (20, 20)), [Entry(word="", x=1, y=1)],
        AppSettings(), [],
    )
    assert words == ["ocr-value"]
    assert seen["run_tesseract"] is live_run
    assert seen["line_box"] is core.line_box
    assert seen["process_ocr_text"] is core.process_ocr_text
