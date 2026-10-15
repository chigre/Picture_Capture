"""Supervised training ZIP must contain the same per-page unified Layout JSON
as the explicit UI diagnostic export; no GUI, private scan, or real OCR needed.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.training_export import make_training_zip
from picture_capture.training_export_composed import write_training_manifest
from picture_capture.training_export_page_understanding import (
    build_export_training_page_with_understanding,
)
from picture_capture.training_export_unified_layout import (
    write_training_unified_layout_diagnostic,
)
import picture_capture.training_export_unified_layout as unified
import picture_capture.training_export_page_understanding as understanding


def _scan(path: Path, rgb: tuple[int, int, int]):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 84), rgb).save(path)
    return path


def _fake_evidence(image, _settings, *, page_index, page_sections, source_image_path):
    return {
        "schema": "picture-capture-ordinary-evidence-v2",
        "enabled": True,
        "image_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
        "candidates": [{"id": f"C{page_index}", "status": "accepted"}],
        "final_lines": [{"x": 5, "y": page_index + 15, "source": "ordinary"}],
        "layout_snapshot": {"physical_rows": [{"role": "entry", "source_y": 15}]},
        "unified_report": {
            "registry": [{"id": f"C{page_index}", "physical_row": {"role": "entry"}}],
            "summary": {"candidates_total": 1},
            "review_queue": [],
        },
        "source_page": Path(source_image_path).name,
        "section_count": len(page_sections),
    }


def test_unified_json_reads_copied_training_image_not_mismatched_live_page(tmp_path, monkeypatch):
    original = _scan(tmp_path / "sources" / "001.png", (230, 20, 10))
    stage = tmp_path / "stage"
    _scan(stage / "images" / original.name, (10, 200, 50))
    observed = []

    def evidence(image, settings, *, page_index, page_sections, source_image_path):
        observed.append((image.getpixel((0, 0)), page_index, source_image_path, page_sections))
        return _fake_evidence(
            image, settings, page_index=page_index,
            page_sections=page_sections, source_image_path=source_image_path,
        )

    from picture_capture import large_head_visual_diagnostics
    monkeypatch.setattr(large_head_visual_diagnostics, "build_large_head_diagnostics", evidence)
    monkeypatch.setattr(unified, "read_page_sections", lambda page: ["real-SECTION"])
    record = write_training_unified_layout_diagnostic(
        original, AppSettings(), stage, 17, "images/001.png",
    )
    assert record["available"] is True
    assert record["json"] == "diagnostics/unified_layout/000017_001_unified_layout.json"
    output = json.loads((stage / record["json"]).read_text(encoding="utf-8"))
    assert observed == [((10, 200, 50), 17, original, ["real-SECTION"])]
    assert output["page_index"] == 17
    assert output["image_size"] == [64, 84]
    assert output["source_page"] == "001.png"
    assert output["unified_report"]["registry"][0]["id"] == "C17"
    assert output["image_sha256"] == hashlib.sha256(
        Image.open(stage / "images/001.png").convert("RGB").tobytes()
    ).hexdigest()
    with Image.open(original) as kept:
        assert kept.getpixel((0, 0)) == (230, 20, 10)


def test_unavailable_layout_still_has_per_page_json_and_manifest_failure_flag(tmp_path, monkeypatch):
    source = _scan(tmp_path / "001.png", (100, 100, 100))
    stage = tmp_path / "stage"
    _scan(stage / "images" / source.name, (100, 100, 100))

    from picture_capture import large_head_visual_diagnostics
    def fail(*_args, **_kwargs):
        raise ValueError("diagnostic unavailable: saved PPP input missing")
    monkeypatch.setattr(large_head_visual_diagnostics, "build_large_head_diagnostics", fail)

    record = write_training_unified_layout_diagnostic(
        source, AppSettings(), stage, 0, "images/001.png",
    )
    diagnostic = json.loads((stage / record["json"]).read_text(encoding="utf-8"))
    assert record["available"] is False
    assert diagnostic["available"] is False
    assert "saved PPP input missing" in diagnostic["error"]
    assert "unified_report" not in diagnostic
    assert diagnostic["page_index"] == 0
    assert diagnostic["image_size"] == [64, 84]


def test_two_same_named_scans_produce_separate_page_indexed_json_files(tmp_path, monkeypatch):
    a = _scan(tmp_path / "a" / "001.png", (200, 50, 50))
    b = _scan(tmp_path / "b" / "001.png", (50, 50, 200))
    stage = tmp_path / "stage"
    _scan(stage / "images" / "a" / "001.png", (200, 50, 50))
    _scan(stage / "images" / "b" / "001.png", (50, 50, 200))
    from picture_capture import large_head_visual_diagnostics
    monkeypatch.setattr(large_head_visual_diagnostics, "build_large_head_diagnostics", _fake_evidence)

    first = write_training_unified_layout_diagnostic(a, AppSettings(), stage, 3, "images/a/001.png")
    second = write_training_unified_layout_diagnostic(b, AppSettings(), stage, 5, "images/b/001.png")
    assert first["json"] != second["json"]
    assert json.loads((stage / first["json"]).read_text())["unified_report"]["registry"][0]["id"] == "C3"
    assert json.loads((stage / second["json"]).read_text())["unified_report"]["registry"][0]["id"] == "C5"


def test_training_composed_page_and_zip_include_unified_json_for_every_page(tmp_path, monkeypatch):
    sources = [
        _scan(tmp_path / "source" / "001.png", (180, 15, 20)),
        _scan(tmp_path / "source" / "002.png", (20, 150, 70)),
    ]
    stage = tmp_path / "staging"
    settings = AppSettings()
    from picture_capture import large_head_visual_diagnostics
    monkeypatch.setattr(large_head_visual_diagnostics, "build_large_head_diagnostics", _fake_evidence)

    # Existing Page Understanding can be unavailable without silently
    # dropping the independent unified diagnostics requested by the user.
    monkeypatch.setattr(
        understanding, "understand_composed_page",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("not a page-design sample")),
    )

    def existing_export(page, project_root, settings, staging_root, index):
        image_target = staging_root / "images" / page.name
        image_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(page, image_target)
        annotation_path = staging_root / "annotations" / (page.stem + ".json")
        annotation_path.parent.mkdir(parents=True, exist_ok=True)
        annotation_path.write_text(
            json.dumps({"page": page.name, "artifacts": {"pdic": "artifacts/001.pdic"}}),
            encoding="utf-8",
        )
        return {
            "page": page.name,
            "annotation": annotation_path.relative_to(staging_root).as_posix(),
            "image": image_target.relative_to(staging_root).as_posix(),
            "ground_truth_count": 1,
        }

    export = build_export_training_page_with_understanding(existing_export)
    records = [export(path, tmp_path, settings, stage, index) for index, path in enumerate(sources)]
    assert len(records) == 2
    for index, rec in enumerate(records):
        assert rec["unified_layout_diagnostic_available"] is True
        diagnostic = stage / rec["unified_layout_diagnostic_json"]
        assert diagnostic.is_file()
        assert json.loads(diagnostic.read_text())["page_index"] == index
        annotation = json.loads((stage / rec["annotation"]).read_text())
        assert annotation["artifacts"]["unified_layout_diagnostic_json"] == rec["unified_layout_diagnostic_json"]
        assert annotation["unified_layout_diagnostics"]["available"] is True
        assert annotation["artifacts"]["pdic"] == "artifacts/001.pdic"
        assert annotation["page_understanding_diagnostics"]["available"] is False

    write_training_manifest(
        stage, project_name="synthetic", settings=settings,
        pages=records, context_files=[], software_version="test",
    )
    zip_path = tmp_path / "dataset.zip"
    make_training_zip(stage, zip_path)
    assert zip_path.exists()
    with ZipFile(zip_path) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("dataset_manifest.json"))
        assert manifest["page_count"] == 2
        for rec in manifest["page_records"]:
            diagnostic_path = rec["unified_layout_diagnostic_json"]
            assert diagnostic_path in names
            payload = json.loads(archive.read(diagnostic_path))
            assert payload["available"] is True
            assert payload["unified_report"]["summary"]["candidates_total"] == 1


def test_unserializable_detector_output_does_not_claim_full_diagnostic(tmp_path, monkeypatch):
    source = _scan(tmp_path / "007.png", (40, 50, 60))
    stage = tmp_path / "staging"
    _scan(stage / "images" / "007.png", (40, 50, 60))
    from picture_capture import large_head_visual_diagnostics
    bad = _fake_evidence(
        Image.new("RGB", (64, 84)), AppSettings(),
        page_index=7, page_sections=[], source_image_path=source,
    )
    bad["unified_report"]["opaque_object"] = object()
    monkeypatch.setattr(
        large_head_visual_diagnostics, "build_large_head_diagnostics",
        lambda *_a, **_k: bad,
    )
    result = write_training_unified_layout_diagnostic(
        source, AppSettings(), stage, 7, "images/007.png",
    )
    assert result["available"] is False
    payload = json.loads((stage / result["json"]).read_text(encoding="utf-8"))
    assert payload["available"] is False
    assert "serialization failed" in payload["error"]
    assert "unified_report" not in payload
