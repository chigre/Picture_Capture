"""Spatial illustrated-dictionary persistence, OCR grouping, export regression."""
from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from picture_capture.illustrated_entries import (
    IllustratedEntry, entry_path, file_ticket, make_entry,
    read_entries, write_entries,
)
from picture_capture.illustrated_export import export_illustrated_index
from picture_capture.illustrated_ocr import (
    SpatialLine, group_spatial_lines, groups_to_entries, join_tesseract_words,
    proposal_overlaps, propose_page_entries, ocr_one_group,
)
from picture_capture.models import AppSettings
from picture_capture.ocr_channel import (
    OcrChannelCandidate, OcrChannelPlan, OcrChannelRecord, OcrChannelResult,
)


def page_at(tmp_path: Path, name="page1.png") -> Path:
    page = tmp_path / name
    Image.new("RGB", (700, 850), "white").save(page)
    return page


def test_multilingual_group_persists_with_stable_id_and_no_legacy_side_effects(tmp_path):
    page = page_at(tmp_path)
    group = replace(make_entry(10, 20, 130, 110), lines=(
        "hair", "les cheveux", "das Haar", "髪の毛", "头发",
    ), primary="hair", aliases=("chevelure",), status="reviewed")
    ticket = write_entries(tmp_path, page, [group], expected_ticket=None,
                           image_size=(700, 850))
    assert ticket == file_ticket(tmp_path, page)
    assert read_entries(tmp_path, page) == [group]
    assert json.loads(entry_path(tmp_path, page).read_text("utf8"))["format"] == \
        "picture-capture-illustrated-entries-v1"
    assert not list(tmp_path.glob("*.pdic"))
    assert not list(tmp_path.rglob("*.rbox"))
    assert not list(tmp_path.rglob("*.ppp"))


def test_manual_edit_and_concurrent_write_guards(tmp_path):
    page = page_at(tmp_path)
    first = make_entry(1, 2, 50, 30)
    ticket = write_entries(tmp_path, page, [first], expected_ticket=None)
    updated = replace(first, lines=("eyebrow", "le sourcil"), primary="eyebrow")
    ticket2 = write_entries(tmp_path, page, [updated], expected_ticket=ticket)
    assert first.id == updated.id and ticket != ticket2
    with pytest.raises(RuntimeError, match="外部变化"):
        write_entries(tmp_path, page, [first], expected_ticket=ticket)
    assert read_entries(tmp_path, page) == [updated]


def test_reject_corrupted_and_cross_page_data_without_overwrite(tmp_path):
    p = page_at(tmp_path)
    q = page_at(tmp_path, "page2.png")
    a = make_entry(30, 30, 40, 20)
    write_entries(tmp_path, p, [a], expected_ticket=None)
    with pytest.raises(ValueError):
        write_entries(tmp_path, p, [replace(a, w=1000)],
                      expected_ticket=file_ticket(tmp_path, p),
                      image_size=(700, 850))
    path = entry_path(tmp_path, q)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(entry_path(tmp_path, p).read_text("utf-8"))
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="页面不匹配"):
        read_entries(tmp_path, q)


def test_project_export_group_vs_split_alias_lookup(tmp_path):
    page = page_at(tmp_path)
    group = replace(make_entry(20, 30, 130, 70), lines=(
        "hair", "les cheveux", "das Haar", "髪の毛", "头发",
    ), primary="hair", aliases=("chevelure",), status="reviewed")
    write_entries(tmp_path, page, [group], expected_ticket=None)
    single, count = export_illustrated_index(tmp_path, [page], split_aliases=False)
    with single.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert count == len(rows) == 1
    assert rows[0]["lookup"] == "hair"
    assert "髪の毛" in json.loads(rows[0]["languages_json"])
    expanded, count = export_illustrated_index(tmp_path, [page], split_aliases=True)
    with expanded.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert count == len(rows) == 6
    assert {v["group_id"] for v in rows} == {group.id}
    assert {v["lookup"] for v in rows} == set(group.lines) | {"chevelure"}


def test_spatial_groups_are_not_sorted_into_columns_or_merged_across_labels():
    labels = [
        SpatialLine("hair", (10, 12, 68, 25)),
        SpatialLine("les cheveux", (12, 29, 90, 42)),
        SpatialLine("das Haar", (11, 46, 78, 59)),
        SpatialLine("forehead", (380, 13, 462, 26)),
        SpatialLine("le front", (382, 31, 445, 44)),
    ]
    groups = group_spatial_lines(labels)
    assert [len(g) for g in groups] == [3, 2]
    results = groups_to_entries(groups)
    assert results[0].lines == ("hair", "les cheveux", "das Haar")
    assert results[1].lines == ("forehead", "le front")
    assert not proposal_overlaps(results[0], results[1])


def test_tesseract_word_boxes_are_joined_only_on_the_same_printed_line():
    words = [
        SpatialLine("les", (5, 10, 26, 22)),
        SpatialLine("cheveux", (30, 10, 80, 22)),
        SpatialLine("das", (5, 30, 27, 42)),
        SpatialLine("Haar", (30, 30, 61, 42)),
    ]
    result = join_tesseract_words(words)
    assert [r.text for r in result] == ["les cheveux", "das Haar"]


def test_full_page_ocr_returns_candidates_only_and_crop_ocr_is_local(tmp_path):
    page = page_at(tmp_path)
    records = (
        OcrChannelRecord("hair", .98, (10, 20, 44, 34)),
        OcrChannelRecord("les cheveux", .95, (11, 38, 92, 52)),
    )
    candidate = OcrChannelCandidate(engine="paddle", records=records, text="hair les cheveux")
    plan = OcrChannelPlan(("paddle",), ("paddle",), lens_mode="off")
    calls = []
    class FakeSession:
        def __init__(self, _settings, *, plan):
            assert "lens" not in plan.enabled_engines

        def recognize_crop(self, _image, *, tesseract_psm):
            calls.append(tesseract_psm)
            return OcrChannelResult(plan, (candidate,))
    settings = AppSettings()
    proposed = propose_page_entries(page, settings, session_factory=FakeSession)
    assert len(proposed) == 1
    assert proposed[0].lines == ("hair", "les cheveux")
    assert proposed[0].status == "draft"
    assert proposed[0].source == "ocr"
    assert not entry_path(tmp_path, page).exists()
    text = ocr_one_group(page, settings, (0, 0, 150, 100),
                         session_factory=FakeSession)
    assert text == ("hair", "les cheveux")
    assert calls == [11, 6]


def test_editor_is_exposed_in_drawing_panel_without_moving_old_pdic_actions():
    from picture_capture.ui import compact_task_menus
    source = Path(compact_task_menus.__file__).read_text(encoding="utf-8")
    assert 'open_illustrated_dictionary_editor(app)' in source
    assert '"主画布文字框编辑 / 校对"' in source
    assert '"全页 OCR 检测与文字组归并"' in source
    assert 'ordinary.pack_forget()' in source
    assert 'illustrated.pack_forget()' in source
    assert '"run_normal_draw_action"' in source
    assert '"refine_lines_selected_scope"' in source
