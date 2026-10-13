"""A real ordinary-drawing replay must include pre-mask and 【】/final stages."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw
import pytest

from picture_capture import processing, processing_core
from picture_capture.layout_illustration_mask import mask_large_illustrations_for_layout
from picture_capture.layout_step_replay_ui import (
    _run_replay, _preview_at_stage, _stage_entries_for_display, _format_stage,
)
from picture_capture.layout_step_trace import LayoutStepTrace
from picture_capture.models import AppSettings, Entry


def _page():
    image = Image.new("RGB", (280, 210), "white")
    draw = ImageDraw.Draw(image)
    for n in range(7):
        y = 17 + 24*n
        draw.rectangle((20, y, 32, y+11), fill="black")
        draw.rectangle((44, y, 105, y+11), fill="black")
    return image


def _settings(**kwargs):
    return AppSettings(
        columns=1, manual_x=15, column_width=180, start_y=7,
        character_height=14, ordinary_auto_layout=False,
        detection_method="left_edge", **kwargs,
    )


def test_replay_runs_exact_ordinary_stage_sequence():
    image = _page()
    settings = _settings()
    pipeline = {}
    try:
        expected, _ = processing.detect_entries(
            image, settings, profile_page_index=0, debug_trace=pipeline,
        )
        timeline, previews = _run_replay(image, settings, 0)
        try:
            keys = [item["key"] for item in timeline.stages]
            assert keys.index("image_preparation") < keys.index("illustration_mask")
            assert keys.index("illustration_mask") < keys.index("raw_estimate")
            assert keys.index("final") < keys.index("layout_role_materialization")
            assert keys[-1] == "final_reading_order"
            assert keys[-2] == "final_y_coordinates_locked"
            final_boundary = timeline.stages[-2]
            assert final_boundary["details"]["move_y"] is False
            assert final_boundary["entries"] == timeline.stages[-1]["entries"]
            assert "不额外平移" in final_boundary["title"]
            emitted = [item["key"] for item in timeline.stages
                       if "entries" in item]
            assert emitted == [step["stage"] for step in pipeline["stages"]]
            final = timeline.stages[-1]["entries"]
            assert [(e["x"], e["y"], e["source"]) for e in final] == [
                (e.x, e.y, e.ocr_source) for e in expected
            ]
            assert timeline.stages[1]["details"]["enabled"] is False
        finally:
            for item in previews.values():
                item.close()
    finally:
        image.close()


def test_cjk_replay_keeps_early_layout_only_shift_before_bracket_and_final_y_lock():
    image = _page()
    settings = _settings(dictionary_profile_id="cjk_visual", ocr_language="ch")
    trace, previews = _run_replay(image, settings, 0)
    try:
        keys = [stage["key"] for stage in trace.stages]
        assert "coherent_separator_y_refinement" in keys
        assert keys.index("layout_role_materialization") < keys.index(
            "coherent_separator_y_refinement"
        )
        assert keys.index("coherent_separator_y_refinement") < keys.index(
            "bracketed_headword_recovery"
        )
        assert keys.index("bracketed_headword_recovery") < keys.index(
            "final_y_coordinates_locked"
        ) < keys.index("final_reading_order")
        early = next(s for s in trace.stages
                     if s["key"] == "coherent_separator_y_refinement")
        assert early["details"]["scope"].startswith("已有 Layout 候选")
        assert "前置" in early["title"]
        final = next(s for s in trace.stages
                     if s["key"] == "final_y_coordinates_locked")
        assert final["details"]["layout_initial_page_shift"] == (
            early["details"]["shift"]
        )
        assert final["details"]["move_y"] is False
    finally:
        for p in previews.values():
            p.close()
        image.close()


def test_mask_candidates_and_unmodified_source_precede_layout(monkeypatch):
    from picture_capture import layout_illustration_mask as masks

    image = _page()
    ImageDraw.Draw(image).rectangle((145, 90, 220, 145), fill="black")
    original_bytes = image.tobytes()
    settings = _settings(layout_mask_illustrations=True)
    settings.character_height = 20
    # Square 80px resembles a display head; 155x160px safely counts as illustration.
    candidates = [
        SimpleNamespace(points=[(3, 5), (83, 5), (83, 85), (3, 85)]),
        SimpleNamespace(points=[(110, 30), (265, 30), (265, 190), (110, 190)]),
    ]
    monkeypatch.setattr(
        processing_core, "detect_illustration_regions_from_image",
        lambda *_args, **_kwargs: candidates,
    )
    try:
        trace, previews = _run_replay(image, settings, 0)
        try:
            masks = next(x for x in trace.stages if x["key"] == "illustration_mask")
            assert masks["details"]["enabled"]
            assert masks["details"]["detected"] == 2
            assert masks["details"]["masked"] == 1
            assert len(masks["candidates"]) == 2
            statuses = {x["status"] for x in masks["candidates"]}
            assert "masked" in statuses
            assert statuses & {"rejected_headlike", "rejected_small"}
            assert sum(x["status"] == "masked" for x in masks["candidates"]) == 1
            assert image.tobytes() == original_bytes
            assert "illustration_mask" in previews
            before = _preview_at_stage(trace.stages, 1, True, previews, image)
            after = _preview_at_stage(trace.stages, 1, False, previews, image)
            # Downscaled preview keeps the page's dimensions for this fixture.
            assert before.getpixel((170, 100)) != (255, 255, 255)
            assert after.getpixel((170, 100)) == (255, 255, 255)
        finally:
            for item in previews.values():
                item.close()
    finally:
        image.close()


def test_mask_enabled_no_regions_still_appears(monkeypatch):
    image = _page()
    settings = _settings(layout_mask_illustrations=True)
    monkeypatch.setattr(
        processing_core, "detect_illustration_regions_from_image",
        lambda *_a, **_k: [],
    )
    trace, previews = _run_replay(image, settings, 0)
    try:
        stage = next(s for s in trace.stages if s["key"] == "illustration_mask")
        assert stage["details"]["enabled"] is True
        assert stage["details"]["masked"] == 0
        assert stage["candidates"] == []
    finally:
        for preview in previews.values():
            preview.close()
        image.close()


def test_bracket_stage_is_not_omitted_and_source_upgrades_are_visible(monkeypatch):
    from picture_capture import ordinary_bracket_pair
    trace = LayoutStepTrace()
    a = Entry("", 20, 55, ocr_source="page_understanding:ordinary_layout_role")
    processing._record_ordinary_debug_stage(
        {"_layout_replay_trace": trace}, "layout_role_materialization", [a],
    )
    a.ocr_source = "ordinary_bracket_pair"
    processing._record_ordinary_debug_stage(
        {"_layout_replay_trace": trace}, "bracketed_headword_recovery", [a],
    )
    stage = trace.stages[-1]
    assert stage["title"] == "【】词头恢复和来源升级"
    assert stage["entries"][0]["source"] == "ordinary_bracket_pair"
    assert stage["entry_changes"][0]["kind"] == "provenance_changed"
    assert _stage_entries_for_display(trace.stages, 1, True)[0]["source"] == (
        "page_understanding:ordinary_layout_role"
    )
    assert "ordinary_bracket_pair" in _format_stage(stage)
    assert [i["role"] for i in trace.history_for_entry(20, 55)] == [
        "page_understanding:ordinary_layout_role", "ordinary_bracket_pair",
    ]


def test_ocr_mode_currently_selected_still_replays_real_ordinary_pipeline():
    image = _page()
    settings = _settings()
    settings.detection_method = "paddleocr"
    try:
        trace, previews = _run_replay(image, settings, 0)
        try:
            assert settings.detection_method == "paddleocr"
            assert trace.stages[-1]["key"] == "final_reading_order"
            assert "bracketed_headword_recovery" not in {
                stage["key"] for stage in trace.stages
            } or any("entries" in stage for stage in trace.stages)
        finally:
            for preview in previews.values():
                preview.close()
    finally:
        image.close()


def test_matched_bracket_shapes_are_frozen_without_changing_detector_output():
    from picture_capture.ordinary_bracket_pair import recover_bracketed_ordinary_entries

    image = Image.new("L", (760, 660), 255)
    pen = ImageDraw.Draw(image)
    # Same physical orientation as real paired 【...】 detector tests.
    for y in (170, 330):
        for closing, base in ((False, 115), (True, 265)):
            if closing:
                pen.rectangle((base+15, y, base+21, y+55), fill=0)
                pen.polygon([(base,y),(base+21,y),(base+21,y+9)], fill=0)
                pen.polygon([(base,y+55),(base+21,y+55),
                             (base+21,y+46)], fill=0)
            else:
                pen.rectangle((base,y,base+6,y+55), fill=0)
                pen.polygon([(base,y),(base+21,y),(base,y+9)],fill=0)
                pen.polygon([(base,y+55),(base+21,y+55),(base,y+46)],fill=0)
    columns = [SimpleNamespace(left=20, right=660)]
    first = recover_bracketed_ordinary_entries([], image, columns, 40, 610, 35)
    evidence = []
    second = recover_bracketed_ordinary_entries(
        [], image, columns, 40, 610, 35, candidate_debug=evidence,
    )
    try:
        assert [(x.x,x.y,x.ocr_source) for x in first] == [
            (x.x,x.y,x.ocr_source) for x in second
        ]
        assert len(first) == 2
        assert any(item["status"] == "accepted" for item in evidence)
        assert {item["bracket_side"] for item in evidence
                if item["status"] == "accepted"} == {"opening", "closing"}
        assert all(len(item["source_box"]) == 4 for item in evidence)
    finally:
        image.close()


def test_bracket_disabled_is_explicitly_labeled_as_skipped():
    image = _page()
    settings = _settings()
    settings.profile_cjk_allow_bracketed_headword = False
    trace, previews = _run_replay(image, settings, 0)
    try:
        keys = [s["key"] for s in trace.stages]
        assert "bracketed_headword_recovery" not in keys
        assert "bracketed_headword_not_run" in keys
        skipped = next(s for s in trace.stages
                       if s["key"] == "bracketed_headword_not_run")
        assert skipped["details"]["profile_cjk_allow_bracketed_headword"] is False
    finally:
        for preview in previews.values():
            preview.close()
        image.close()


def test_optional_mask_diagnostics_do_not_change_default_pixels_or_decisions():
    image = Image.new("RGB", (320, 280), (120, 120, 120))
    settings = AppSettings(layout_mask_illustrations=True, character_height=20, column_width=300)
    regions = [
        SimpleNamespace(points=[(10,10),(90,10),(90,90),(10,90)]),
        SimpleNamespace(points=[(120,40),(300,40),(300,250),(120,250)]),
    ]
    detector = lambda *_a, **_k: regions
    old, old_stats = mask_large_illustrations_for_layout(
        image, settings, detector=detector,
    )
    candidates = []
    new, new_stats = mask_large_illustrations_for_layout(
        image, settings, detector=detector, candidate_debug=candidates,
    )
    try:
        assert old_stats == new_stats
        assert old.tobytes() == new.tobytes()
        assert [item["status"] for item in candidates] == [
            "rejected_headlike", "masked",
        ]
    finally:
        old.close()
        new.close()
        image.close()
