"""Round 26: page geometry, spawn-safe detection and illustration file jobs."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from PIL import Image

from picture_capture import processing_core as core
from picture_capture.models import AppSettings, Entry
from picture_capture.geometry import page_runtime_context
from picture_capture.detection import spawn_job_execution
from picture_capture.illustration import source_detection_jobs


def test_round26_owners_and_historical_signatures():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(pkg.glob("*.py"))) == 9
    expected = {
        "geometry/page_runtime_context.py": {"page_geometry_context"},
        "detection/spawn_job_execution.py": {"detect_entries_job_impl"},
        "illustration/source_detection_jobs.py": {
            "detect_illustration_regions_impl", "detect_illustrations_job_impl",
        },
    }
    for filename, defs in expected.items():
        leaf = pkg / filename
        assert leaf.is_file() and not (pkg / leaf.name).exists()
        parsed = ast.parse(leaf.read_text(encoding="utf-8"))
        assert {node.name for node in parsed.body if isinstance(node, ast.FunctionDef)} == defs
        assert not any(
            isinstance(node, (ast.ClassDef, ast.Assign, ast.AnnAssign))
            for node in parsed.body
        )
    for fn in ("_page_geometry_context", "detect_entries_job",
               "detect_illustration_regions", "detect_illustrations_job"):
        assert getattr(core, fn).__module__ == "picture_capture.processing_core"
    assert list(inspect.signature(core._page_geometry_context).parameters) == [
        "image", "settings", "profile_page_index",
    ]
    assert list(inspect.signature(core.detect_entries_job).parameters) == [
        "image_path", "settings", "pages", "profile_page_index",
    ]
    assert list(inspect.signature(core.detect_illustration_regions).parameters) == [
        "image_path", "settings", "analysis_column_width", "profile_page_index",
    ]
    assert list(inspect.signature(core.detect_illustrations_job).parameters) == [
        "image_path", "settings", "profile_page_index",
    ]


def test_page_geometry_core_supplies_live_layout_pipeline(monkeypatch):
    img = Image.new("RGB", (35, 25), "white")
    settings = AppSettings()
    hits = []
    def normalizer(arg):
        hits.append("rgb")
        assert arg is img
        return arg
    def effective(arg, dims, page):
        hits.append("profile")
        assert dims == img.size and page == 3
        return settings
    def analysis(arg, _settings, _index):
        hits.append("mask")
        return arg
    def geometry(arg, _settings):
        hits.append("geometry")
        return "layout"
    monkeypatch.setattr(core, "normalize_page_rgb", normalizer)
    monkeypatch.setattr(core, "effective_page_settings", effective)
    monkeypatch.setattr(core, "page_template_analysis_image", analysis)
    monkeypatch.setattr(core, "derive_geometry", geometry)
    assert core._page_geometry_context(img, settings, 3) == (
        img, settings, img, "layout",
    )
    assert hits == ["rgb", "profile", "mask", "geometry"]


def test_spawn_detection_job_preserves_pdic_coordinates_and_page_metadata(monkeypatch, tmp_path):
    image_path = tmp_path / "page.png"
    Image.new("RGB", (90, 50), "white").save(image_path)
    rows = [Entry(word="字", x=17, y=29)]
    observed = {}
    monkeypatch.setattr(core, "read_page_sections", lambda page: ["section"])
    def fake_detect(image, settings, *, profile_page_index, page_sections):
        observed["detect"] = (image.size, profile_page_index, page_sections)
        return rows, None
    def fake_write(path, entries, image_width, pages):
        observed["write"] = (path, entries, image_width, pages)
    monkeypatch.setattr(core, "detect_entries", fake_detect)
    monkeypatch.setattr(core, "write_pdic", fake_write)
    settings = AppSettings()
    num = core.detect_entries_job(str(image_path), settings, ("A", "B", "C"), 2)
    assert num == 1
    assert settings.detection_method == "left_edge"
    assert observed["detect"] == ((90, 50), 2, ["section"])
    assert observed["write"][1:] == (rows, 90, ("A", "B", "C"))
    assert observed["write"][0] == core.pdic_path_for_image(image_path)
    assert (rows[0].x, rows[0].y) == (17, 29)


def test_file_illustration_detect_and_spawn_job_share_active_core_callbacks(monkeypatch, tmp_path):
    image_path = tmp_path / "page.png"
    Image.new("RGB", (30, 20), "white").save(image_path)
    observed = []
    def detect(image, settings, *, analysis_column_width, profile_page_index):
        observed.append((image.size, analysis_column_width, profile_page_index))
        return ["found"]
    monkeypatch.setattr(core, "detect_illustration_regions_from_image", detect)
    settings = AppSettings()
    assert core.detect_illustration_regions(
        image_path, settings, analysis_column_width=130, profile_page_index=4,
    ) == ["found"]
    assert observed == [((30, 20), 130, 4)]
    monkeypatch.setattr(core, "detect_illustrations_to_ppp",
                        lambda page, config, *, profile_page_index: {
                            "page": str(page), "index": profile_page_index,
                        })
    job = core.detect_illustrations_job(str(image_path), settings, 5)
    assert job == {"page": str(image_path), "index": 5}
