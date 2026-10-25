"""Round 24: crop-publishing owners keep source bounds and live transaction seams."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from PIL import Image

from picture_capture import processing_core as core
from picture_capture.models import AppSettings, Entry
from picture_capture.crop import (
    illustration_export, illustration_source_bounds, single_line_export,
)


def test_crop_algorithm_ownership_and_source_compatibility():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(pkg.glob("*.py"))) == 7
    owners = {
        "illustration_export.py": "split_illustrations_impl",
        "illustration_source_bounds.py": "illustration_crop_bounds_impl",
        "single_line_export.py": "split_single_lines_impl",
    }
    for filename, function in owners.items():
        path = pkg / "crop" / filename
        assert path.is_file()
        assert not (pkg / filename).exists()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert [n.name for n in tree.body if isinstance(n, ast.FunctionDef)] == [function]
        assert not any(isinstance(n, (ast.Assign, ast.AnnAssign, ast.ClassDef)) for n in tree.body)
    assert core.split_illustrations.__module__ == "picture_capture.processing_core"
    assert core.illustration_crop_bounds.__module__ == "picture_capture.processing_core"
    assert core.split_single_lines.__module__ == "picture_capture.processing_core"
    assert list(inspect.signature(core.split_illustrations).parameters) == [
        "image_path", "polygons", "output_dir", "settings", "top_y", "bottom_y",
        "margin", "entries", "entry_left_padding", "entry_right_padding",
        "integrate_illustrations", "profile_page_index", "page_sections",
        "transparent_background", "previous_entry_ref",
    ]
    assert list(inspect.signature(core.illustration_crop_bounds).parameters) == [
        "image", "settings", "top_y", "bottom_y", "margin", "page_sections",
    ]
    assert list(inspect.signature(core.split_single_lines).parameters) == [
        "image_path", "entries", "settings", "output_dir",
        "profile_page_index", "page_sections", "write_manifest",
    ]


def test_illustration_bounds_uses_source_image_pixels_and_live_scaler(monkeypatch):
    settings = AppSettings()
    settings.layout_transform = "identity"
    image = Image.new("RGB", (80, 50), "white")
    old = core._source_px
    seen = []
    def scaler(value):
        seen.append(value)
        return old(value)
    monkeypatch.setattr(core, "_source_px", scaler)
    got = core.illustration_crop_bounds(
        image, settings, top_y=9, bottom_y=0, margin=4,
    )
    assert got == (old(9), 50, old(4))
    assert seen and 9 in seen and 4 in seen


def test_illustration_export_keeps_transaction_and_plan_hooks(monkeypatch, tmp_path):
    seen = {}
    def fake_impl(*args, deps, **kwargs):
        seen.update(deps)
        assert kwargs["transparent_background"] is True
        return "stub-result"
    monkeypatch.setattr(illustration_export, "split_illustrations_impl", fake_impl)
    fake_publish = lambda *a, **kw: None
    monkeypatch.setattr(core, "_publish_file_transaction", fake_publish)
    result = core.split_illustrations(
        tmp_path / "page.png", [], tmp_path,
        transparent_background=True,
    )
    assert result == "stub-result"
    assert seen["_publish_file_transaction"] is fake_publish
    assert seen["_stage_page_crop_plan"] is core._stage_page_crop_plan
    assert seen["build_page_crop_plan"] is core.build_page_crop_plan
    assert seen["IllustrationSplitResult"] is core.IllustrationSplitResult


def test_single_line_export_keeps_current_stage_and_publish_hooks(monkeypatch, tmp_path):
    seen = {}
    def fake_impl(*args, deps, **kwargs):
        seen.update(deps)
        assert kwargs["write_manifest"] is False
        return ["sentinel"]
    monkeypatch.setattr(single_line_export, "split_single_lines_impl", fake_impl)
    fake_stage = lambda *a, **kw: ("box", "stage")
    monkeypatch.setattr(core, "_stage_crop", fake_stage)
    result = core.split_single_lines(
        tmp_path / "page.png", [Entry(word="汉", x=2, y=3)],
        AppSettings(), tmp_path, write_manifest=False,
    )
    assert result == ["sentinel"]
    assert seen["_stage_crop"] is fake_stage
    assert seen["_publish_file_transaction"] is core._publish_file_transaction
    assert seen["CropRecord"] is core.CropRecord
