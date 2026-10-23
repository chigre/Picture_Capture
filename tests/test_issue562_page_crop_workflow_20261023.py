"""Issue #562: integrated whole-entry crop planning and atomic publishing owner."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from PIL import Image, ImageChops
import pytest

from picture_capture import processing_core as core
from picture_capture.crop import page_workflow as owner
from picture_capture.models import AppSettings


def test_leaf_import_isolated_from_core_and_gui():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.crop.page_workflow import CropWorkflowDeps
assert 'picture_capture.processing_core' not in sys.modules
assert 'picture_capture.processing' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


def test_live_dependencies_preserve_historical_public_models():
    deps = core._crop_workflow_deps()
    assert deps.CropRecord is core.CropRecord
    assert deps.PageCropPlan is core.PageCropPlan
    assert deps.EntryCropPiecePlan is core.EntryCropPiecePlan
    assert deps.IllustrationCropPlan is core.IllustrationCropPlan
    assert core.PageCropPlan.__module__ == "picture_capture.processing_core"
    assert core.CropRecord.__module__ == "picture_capture.processing_core"
    assert hasattr(owner, "build_page_crop_plan")
    assert hasattr(owner, "split_whole_entries")


def _poly(name, points):
    return SimpleNamespace(name=name, points=points)


def test_one_plan_links_contained_partial_and_standalone_polygons(monkeypatch):
    image = Image.new("RGB", (80, 90), "white")
    entries = [SimpleNamespace(word="Atlas")]
    original_piece = core.EntryCropPiecePlan(
        0, 0, "Atlas", (10, 10, 30, 50), "(1)")
    monkeypatch.setattr(core, "_base_entry_crop_pieces",
                        lambda *a, **kw: (entries, [original_piece]))
    monkeypatch.setattr(core, "effective_page_settings",
                        lambda settings, size, index: settings)
    monkeypatch.setattr(core, "illustration_crop_bounds",
                        lambda *a, **kw: (0, 90, 0))
    monkeypatch.setattr(core, "illustration_polygon_box",
                        lambda image, region, **kw: (
                            min(x for x, y in region.points),
                            min(y for x, y in region.points),
                            max(x for x, y in region.points),
                            max(y for x, y in region.points)))
    monkeypatch.setattr(core, "polygon_display_name",
                        lambda region, index: region.name)
    monkeypatch.setattr(core, "canonical_polygon_link",
                        lambda region: None)
    monkeypatch.setattr(core, "_polygon_bbox",
                        lambda region: (
                            min(x for x, y in region.points),
                            min(y for x, y in region.points),
                            max(x for x, y in region.points),
                            max(y for x, y in region.points)))
    regions = [
        _poly("Atlas", [(12, 15), (20, 15), (20, 25), (12, 25)]),
        _poly("Atlas", [(25, 20), (40, 20), (40, 30), (25, 30)]),
        _poly("Detached", [(55, 30), (70, 30), (70, 40), (55, 40)]),
    ]
    try:
        plan = core.build_page_crop_plan(
            image, entries, regions, AppSettings(),
            integrate_illustrations=True)
        assert isinstance(plan, core.PageCropPlan)
        assert [(item.associated_entry_index, item.relation, item.standalone)
                for item in plan.illustrations] == [
                    (0, "contained", False),
                    (0, "partial", False),
                    (None, "unassociated", True),
                ]
        assert plan.entry_pieces[0].source_mode == "linked_original"
        assert plan.entry_pieces[0].merge_polygon_indices == (1,)
        assert plan.entry_pieces[0] is original_piece
    finally:
        image.close()


def test_plan_write_uses_live_staging_and_transaction(monkeypatch, tmp_path):
    calls = []
    staged = tmp_path / "tmp-plan"
    output = tmp_path / "plan.json"
    monkeypatch.setattr(core, "_stage_page_crop_plan",
                        lambda root, stem, plan: (staged, output))
    monkeypatch.setattr(core, "_publish_file_transaction",
                        lambda changes, **kw: calls.append((changes, kw)))
    path = core.write_page_crop_plan(
        tmp_path, "sample", core.PageCropPlan([], []))
    assert path is output
    assert calls == [([(staged, output)], {})]


def test_whitefill_polygons_preserves_source_and_renders_white():
    source = Image.new("RGB", (30, 30), "black")
    region = _poly("photo", [(4, 4), (18, 4), (18, 18), (4, 18)])
    out = core._whitefill_polygons(source, [region])
    assert source.getpixel((10, 10)) == (0, 0, 0)
    assert out.getpixel((10, 10)) == (255, 255, 255)
    assert out.getpixel((25, 25)) == (0, 0, 0)
    out.close()
    source.close()


def _single_piece_plan():
    return core.PageCropPlan(
        [core.EntryCropPiecePlan(0, 0, "Atlas", (3, 4, 28, 32), "(1)")],
        [])


def test_export_end_to_end_publishes_crop_manifest_widths_and_plan(
    monkeypatch, tmp_path
):
    original = tmp_path / "source.png"
    Image.new("RGB", (50, 60), (9, 19, 29)).save(original)
    captured = []
    monkeypatch.setattr(core, "build_page_crop_plan",
                        lambda *a, **kw: (captured.append(kw), _single_piece_plan())[1])
    monkeypatch.setattr(core, "read_page_sections", lambda path: [])
    monkeypatch.setattr(core, "read_auxiliary_lines", lambda path: [])
    outdir = tmp_path / "outputs"
    records = core.split_whole_entries(
        original, [SimpleNamespace(word="Atlas")], AppSettings(), outdir,
        integrate_illustrations=False)
    assert len(captured) == 1
    assert captured[0]["integrate_illustrations"] is False
    assert len(records) == 1 and isinstance(records[0], core.CropRecord)
    cropped = Image.open(outdir / records[0].filename)
    try:
        assert cropped.size == (25, 28)
    finally:
        cropped.close()
    assert (outdir / "source.PWWords").read_text(encoding="utf-8").count("Atlas") == 1
    widths = json.loads((outdir / "source.PWWWidths.json").read_text(encoding="utf-8"))
    assert widths[records[0].filename] == 25
    assert not list(outdir.glob("*.tmp"))


def test_failed_export_cleans_staged_crops_without_publication(
    monkeypatch, tmp_path
):
    original = tmp_path / "source.png"
    Image.new("RGB", (50, 60), "white").save(original)
    monkeypatch.setattr(core, "build_page_crop_plan",
                        lambda *a, **kw: _single_piece_plan())
    monkeypatch.setattr(core, "read_page_sections", lambda path: [])
    monkeypatch.setattr(core, "read_auxiliary_lines", lambda path: [])
    def reject_manifest(*a, **kw):
        raise RuntimeError("staging failure")
    monkeypatch.setattr(core, "_stage_text_file", reject_manifest)
    outdir = tmp_path / "outputs"
    with pytest.raises(RuntimeError, match="staging failure"):
        core.split_whole_entries(
            original, [SimpleNamespace(word="Atlas")], AppSettings(), outdir,
            integrate_illustrations=False)
    assert not list(outdir.glob("*"))
