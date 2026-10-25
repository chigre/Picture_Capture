"""Issue #562: combined-mode Entry mapping, ordinary layout and marker crops."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from picture_capture import processing as public_processing
from picture_capture import processing_core as core
from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary import auto_layout_policy, fusion_entry_mapping
from picture_capture.ocr import ordinary_marker_crop

PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_large_batch_paths_and_original_core_identities():
    assert len(list(PKG.glob("*.py"))) == 7
    for path in (
        "ordinary/auto_layout_policy.py",
        "ordinary/fusion_entry_mapping.py",
        "ocr/ordinary_marker_crop.py",
        "ocr/line_structure_repairs.py",
    ):
        assert (PKG / path).is_file()
        assert not (PKG / Path(path).name).exists()
    for fn in (
        core.ordinary_page_layout_settings, core._entry_with_fused_metadata,
        core._review_candidate_to_entry, core._ordinary_marker_local_crop,
    ):
        assert fn.__module__ == "picture_capture.processing_core"
    assert list(inspect.signature(core._review_candidate_to_entry).parameters) == ["candidate"]
    assert list(inspect.signature(core._entry_with_fused_metadata).parameters) == [
        "position", "semantic", "use_semantic_position",
    ]
    assert list(inspect.signature(core._ordinary_marker_local_crop).parameters) == [
        "canonical", "entry", "geometry", "settings", "row_metrics", "source_image",
    ]
    assert core.Entry is Entry
    assert Entry.__module__ == "picture_capture.models"


def test_auto_layout_disabled_is_copy_and_no_detector_call():
    img = Image.new("RGB", (20, 30), "white")
    settings = AppSettings()
    settings.ordinary_auto_layout = False
    out, applied = core.ordinary_page_layout_settings(img, settings)
    assert out is not settings
    assert applied == {}
    assert out.ordinary_auto_layout is False


def test_auto_layout_enabled_respects_field_switches_and_current_public_hook(monkeypatch):
    from picture_capture.layout import detection, parameter_evidence

    img = Image.new("RGB", (20, 30), "white")
    settings = AppSettings()
    settings.ordinary_auto_layout = True
    settings.ordinary_auto_columns = False
    settings.ordinary_auto_start_y = True
    settings.start_y = 11
    settings.manual_columns = True
    calls = []
    def detector(image, effective):
        calls.append((image.size, effective.layout_columns_policy))
        return SimpleNamespace(start_y=54, columns=3, row_padding=23)
    monkeypatch.setattr(detection, "detect_layout_parameters", detector)
    monkeypatch.setattr(parameter_evidence, "row_padding_is_measured", lambda estimate: False)
    old_fields = core.ORDINARY_AUTO_LAYOUT_FIELDS
    monkeypatch.setattr(public_processing, "ORDINARY_AUTO_LAYOUT_FIELDS",
                        (("start_y", "ordinary_auto_start_y"),))
    out, applied = core.ordinary_page_layout_settings(img, settings)
    assert applied == {"start_y": 54}
    assert out.start_y == 54 and settings.start_y == 11
    assert out.manual_columns is False
    assert calls == [((20, 30), settings.layout_columns_policy)]
    monkeypatch.setattr(public_processing, "ORDINARY_AUTO_LAYOUT_FIELDS", old_fields)


def test_fused_metadata_preserves_position_and_ocr_fields(monkeypatch):
    anchor = Entry(word="", x=10, y=20)
    semantic = Entry(
        word="詞", x=30, y=40, ocr_source="paddle",
        candidate_id="cand1", final_engine="paddle",
        alphabetical_warning="alphabetical_backtrack_vs:abc",
        issue_type="needs_review", ocr_single_cjk=True,
    )
    left = core._entry_with_fused_metadata(anchor, semantic)
    right = core._entry_with_fused_metadata(
        anchor, semantic, use_semantic_position=True,
    )
    assert (left.x, left.y, left.word) == (10, 20, "詞")
    assert (right.x, right.y) == (30, 40)
    assert left.ocr_source == "combined:paddle"
    assert left.ocr_single_cjk is True and left.candidate_id == "cand1"
    assert left == fusion_entry_mapping.entry_with_fused_metadata(
        anchor, semantic, entry_cls=Entry,
    )
    calls = []
    def patched_entry(**kwargs):
        calls.append(kwargs)
        return Entry(**kwargs)
    monkeypatch.setattr(public_processing, "Entry", patched_entry)
    assert core._entry_with_fused_metadata(anchor, semantic).word == "詞"
    assert len(calls) == 1
    monkeypatch.setattr(public_processing, "Entry", Entry)


def test_review_candidate_to_entry_filters_invalid_and_carries_metadata():
    for row in (
        {"position_variant": "original", "source_x": 4, "source_y": 20},
        {"source_x": "oops", "source_y": 20},
        {"source_x": 5, "source_y": 0},
    ):
        assert core._review_candidate_to_entry(row) is None
    candidate = {
        "source_x": 14, "source_y": 62, "position_variant": "refined",
        "word": "漢", "final_engine": "paddle", "candidate_id": "c-1",
        "paddle": {"lemma": "漢", "features": {
            "cjk_single_visual": True, "cjk_oversized_recovery": True,
            "line_height_reference": 18,
        }},
        "issue_types": ["review", "visual"],
        "box": [2, 30, 18, 59], "confidence": 0.91, "score": 0.84,
    }
    entry = core._review_candidate_to_entry(candidate)
    assert type(entry) is Entry
    assert (entry.x, entry.y, entry.word) == (14, 62, "漢")
    assert entry.ocr_source == "latent:paddle"
    assert entry.ocr_single_cjk and entry.ocr_oversized_cjk
    assert entry.ocr_box_height == 29
    assert entry.issue_type == "review,visual"
    assert entry == fusion_entry_mapping.review_candidate_to_entry(
        candidate, entry_cls=Entry,
    )


def test_marker_crop_keeps_physical_source_pixels_and_oversized_flag(monkeypatch):
    from picture_capture.proofreading import classification
    from picture_capture.ocr import entry_crop, entry_visual_scale

    monkeypatch.setattr(classification, "get_entry_classification",
                        lambda entry: SimpleNamespace(entry_scale="regular"))
    monkeypatch.setattr(entry_crop, "entry_ocr_crop_box",
                        lambda *args, **kwargs: (2, 3, 12, 15))
    visual = {"height": 0}
    monkeypatch.setattr(entry_visual_scale, "visual_oversized_head_height",
                        lambda *args, **kwargs: visual["height"])
    geometry = SimpleNamespace(
        source_size=(40, 30),
        transform=SimpleNamespace(
            canonical_box_to_source=lambda box, size: box,
        ),
    )
    canonical = Image.new("RGB", (40, 30), "white")
    source = Image.new("RGB", (40, 30), "black")
    entry = Entry(word="", x=7, y=8)
    settings = SimpleNamespace(character_height=20, layout_writing_mode="horizontal-tb")
    output, is_large = core._ordinary_marker_local_crop(
        canonical, entry, geometry, settings, source_image=source,
    )
    assert output.size == (10, 12)
    assert output.getpixel((0, 0)) == (0, 0, 0)
    assert not is_large
    output.close()
    settings.layout_writing_mode = "vertical-rl"
    visual["height"] = 25
    output, is_large = core._ordinary_marker_local_crop(
        canonical, entry, geometry, settings, source_image=source,
    )
    assert output.getpixel((0, 0)) == (255, 255, 255)
    assert is_large
    output.close()
