"""Issue #562 / Round 41: v2 training export physically owned by training package."""
from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from picture_capture import training_export as facade
from picture_capture.models import AppSettings
from picture_capture.training import export_page_v2, export_composed
from picture_capture.training import ground_truth_matching, manifest_v2, zip_publish

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_round41_v2_export_implementation_in_training_package_and_legacy_abi():
    legacy = (ROOT / "training_export.py").read_text(encoding="utf-8")
    owner = (ROOT / "training/export_page_v2.py").read_text(encoding="utf-8")
    assert "_page_v2.export_training_page(" in legacy
    assert "def export_training_page(" in legacy
    assert "def export_training_page(" in owner
    assert '"ground_truth_lines": ground_truth' in owner
    assert '"illustration_polygons": [' in owner
    assert '"ocr_trace": {' in owner
    assert "source_column_paths_xy" in owner
    assert '"page_template": {' in owner
    assert '"layout": {' in owner
    assert '"format": TRAINING_EXPORT_FORMAT' in owner
    assert '"ground_truth_lines": ground_truth' not in legacy
    assert "from ..training_export" not in owner
    assert "from .training.ground_truth_matching import _candidate_ground_truth_link" in legacy
    assert facade._candidate_ground_truth_link is ground_truth_matching._candidate_ground_truth_link
    assert facade.make_training_zip is zip_publish.make_training_zip
    assert facade.TrainingExportCancelled is zip_publish.TrainingExportCancelled
    assert facade.write_training_manifest is manifest_v2.write_training_manifest
    assert export_composed._export_training_page_v2 is facade.export_training_page
    assert list(inspect.signature(facade.export_training_page).parameters) == [
        "page", "project_root", "settings", "staging_root", "page_index"
    ]
    owner_function = next(n for n in ast.parse(owner).body
                          if isinstance(n, ast.FunctionDef) and n.name == "export_training_page")
    assert len(owner_function.body) > 10


def test_round41_root_export_delegates_live_patch_seams(monkeypatch):
    calls = []
    def collector(page, project_root, settings, staging_root, page_index, *, deps):
        calls.append((page, project_root, settings, staging_root, page_index, deps))
        return {"page": "compat"}
    monkeypatch.setattr(export_page_v2, "export_training_page", collector)
    patched = lambda row, truths, geom, height: {"owner": "patched"}
    monkeypatch.setattr(facade, "_candidate_ground_truth_link", patched)
    page = Path("page.png")
    project = Path("project")
    staging = Path("stage")
    settings = AppSettings()
    assert facade.export_training_page(page, project, settings, staging, 4) == {"page": "compat"}
    assert calls[0][:5] == (page, project, settings, staging, 4)
    dependencies = calls[0][5]
    assert dependencies["_candidate_ground_truth_link"] is patched
    for name in (
        "Image", "json", "shutil", "normalize_page_rgb", "effective_page_settings",
        "page_template_analysis_image", "derive_geometry", "pdic_path", "read_pdic",
        "read_ppp", "column_index", "SOURCE_COORDINATE_SPACE", "ocr_cache_root",
        "_read_json", "coordinate_contract", "TRAINING_EXPORT_FORMAT",
    ):
        assert dependencies[name] is getattr(facade, name)


def test_round41_source_pixel_export_with_saved_pdic_ppp_and_ocr_cache(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    page = project / "0001.png"
    Image.new("RGB", (80, 100), "white").save(page)
    pdic = project / "0001.PDIC"
    pdic.write_text("test annotated data", encoding="utf-8")
    ppp = project / "0001.PPP"
    ppp.write_text("test polygon data", encoding="utf-8")
    cache_dir = project / "ocr"
    cache_dir.mkdir()
    (cache_dir / "0001.json").write_text(json.dumps({
        "review_candidates": [{"id": "A", "source_x": 12, "source_y": 27}],
        "manual_override_count": 2, "page_quality": {"status": "ok"},
    }), encoding="utf-8")
    (cache_dir / "0001_manual_selection.json").write_text(
        '{"manual": true}', encoding="utf-8"
    )
    geom = SimpleNamespace(
        column_starts=[0], column_paths=[],
        transform=SimpleNamespace(kind="identity", canonical_size=lambda size: size),
    )
    monkeypatch.setattr(facade, "derive_geometry", lambda img, settings: geom)
    monkeypatch.setattr(facade, "effective_page_settings",
                        lambda settings, size, index: SimpleNamespace(character_height=24, row_padding=3))
    monkeypatch.setattr(facade, "page_template_analysis_image", lambda img, settings, index: img)
    monkeypatch.setattr(facade, "column_index", lambda x, geometry, y: 0)
    monkeypatch.setattr(facade, "pdic_path", lambda page: pdic)
    monkeypatch.setattr(facade, "read_pdic",
                        lambda path: [SimpleNamespace(x=12, y=27, word="example")])
    monkeypatch.setattr(facade, "ppp_read_path_for_image", lambda page: ppp)
    monkeypatch.setattr(facade, "read_ppp",
                        lambda path: [SimpleNamespace(label="illustration", points=[(2, 3), (4, 5)])])
    monkeypatch.setattr(facade, "ocr_cache_root", lambda root: cache_dir)
    monkeypatch.setattr(facade, "_candidate_ground_truth_link",
                        lambda row, truth, geometry, height: {"matched": len(truth), "height": height})
    monkeypatch.setattr(facade, "excluded_source_side", lambda settings, index: "left")
    monkeypatch.setattr(facade, "excluded_source_side_percent", lambda settings, index: 12.5)
    output = tmp_path / "training"
    result = facade.export_training_page(page, project, AppSettings(), output, 3)
    data = json.loads((output / result["annotation"]).read_text(encoding="utf-8"))
    assert result["page"] == "0001.png"
    assert result["ground_truth_count"] == 1
    assert result["polygon_count"] == 1
    assert result["ocr_candidate_count"] == 1
    assert result["ocr_cache_available"] is True
    assert data["format"] == manifest_v2.TRAINING_EXPORT_FORMAT
    assert data["ground_truth_lines"][0]["word"] == "example"
    assert data["ground_truth_lines"][0]["source_x"] == 12
    assert data["ground_truth_lines"][0]["source_y"] == 27
    assert data["illustration_polygons"][0]["source_points_xy"] == [[2, 3], [4, 5]]
    assert data["ocr_trace"]["candidates"][0]["matched"] == 1
    assert data["ocr_trace"]["candidates"][0]["height"] == 24
    assert data["ocr_trace"]["manual_selection"] == {"manual": True}
    assert data["page_template"]["excluded_side"] == "left"
    assert data["page_template"]["side_boundary_x"] == 10
    assert data["layout"]["transform_used_internally"] == "identity"
    assert (output / data["image"]["file"]).exists()
    assert (output / data["artifacts"]["pdic"]).read_text(encoding="utf-8") == "test annotated data"
    assert (output / data["artifacts"]["ppp"]).read_text(encoding="utf-8") == "test polygon data"
    assert (output / "ocr/0001.json").exists()
