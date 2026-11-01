"""G3 R4.2: retain no-hit page source witnesses for the entire scan epoch.

Synthetic files only. No real dictionary, OCR data or persistence writes.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from picture_capture.persistence.project_storage import page_sections_read_path_for_image
from picture_capture.ui import focused_filter_workflow as workflow


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


@pytest.mark.parametrize("mutation", ("pdic", "ocr", "section"))
def test_no_hit_page_source_drift_before_epoch_terminal_is_rejected(tmp_path, mutation, monkeypatch):
    verify_calls = []
    original_verify = workflow.verify_focused_scan_source

    def tracked_verify(page, pdic_path, cache_path, expected):
        verify_calls.append(Path(page))
        return original_verify(page, pdic_path, cache_path, expected)

    monkeypatch.setattr(workflow, "verify_focused_scan_source", tracked_verify)

    pages = [tmp_path / f"{index:03d}.png" for index in range(1, 5)]
    ocr_root = tmp_path / "ocr-cache"
    ocr_root.mkdir()
    pdic_paths = {}
    ocr_paths = {}
    section_paths = {}
    for page in pages:
        Image.new("RGB", (8, 8), "white").save(page)
        pdic_paths[page] = page.with_suffix(".pdic")
        pdic_paths[page].write_bytes(f"pdic-{page.stem}-before".encode())
        ocr_paths[page] = ocr_root / f"{page.stem}.json"
        ocr_paths[page].write_text('{"review_candidates": []}', encoding="utf-8")
        section_paths[page] = page_sections_read_path_for_image(page)
        section_paths[page].parent.mkdir(parents=True, exist_ok=True)
        section_paths[page].write_bytes(f"section-{page.stem}-before".encode())

    calls = []
    status, indicator = _Var(""), _Var("")
    def read_pdic(path):
        # Page 001 is deliberately a valid no-hit page; the other pages
        # provide one target each so the streaming scan crosses two chunks.
        if path.stem == "001":
            return []
        return [SimpleNamespace(word="fixture", x=13, y=27)]

    parent = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path, images=pages),
        current_page=pages[0],
        status_var=status,
        settings=SimpleNamespace(character_height=18),
        _project_words=[],
        _parse_page_spec=lambda _value: [0, 1, 2, 3],
        _invalidate_ui_worker=lambda _key: None,
        _start_ui_worker=lambda *args: calls.append(args) or len(calls),
    )
    review = SimpleNamespace(
        parent=parent,
        _filter_rows_active=True,
        _filter_save_running=False,
        _filter_pending_changes={},
        _filter_scan_serial=10,
        _filter_render_serial=4,
        _filter_batch_render_cache={},
        _filter_prefetch_key=None,
        _review_render_worker_key="review-initial",
        review_mode_var=_Var("filter"),
        filter_batch_var=indicator,
        focused_page_range_var=_Var("1-4"),
        focused_include_mismatch_var=_Var(False),
        focused_include_characters_var=_Var(False),
        focused_exclude_single_var=_Var(False),
        focused_exclude_reference_var=_Var(False),
        focused_risk_priority_var=_Var(False),
        focused_timing_var=_Var(False),
        focused_characters_var=_Var(""),
        focused_batch_size_var=_Var("1"),
        review_ocr_compare_var=_Var("fusion"),
        OCR_COMPARE_LABEL_TO_KEY={"fusion": "fusion"},
        _persist_focused_filter_settings=lambda: None,
        _set_filter_navigation=lambda _enabled: None,
        _focused_batch_size=lambda: 1,
        _filter_available_target_count=lambda: len(review.filtered_targets),
        _clear_review_workspace=lambda _message: None,
        _update_title=lambda: None,
        _update_filter_batch_indicator=lambda: None,
        _request_filter_batch_render=lambda: None,
        _schedule_filter_next_batch_preload=lambda: None,
        _review_image_area_width=lambda: 300,
        review_zoom_auto=False,
        review_zoom=1.0,
    )
    deps = SimpleNamespace(
        messagebox=SimpleNamespace(
            showerror=lambda *a, **k: None,
            showinfo=lambda *a, **k: None,
        ),
        _focused_review_character_tokens=lambda _value: (),
        read_pdic=read_pdic,
        pdic_path=lambda page: pdic_paths[page],
        ocr_cache_root=lambda _root: ocr_root,
        json=json,
        _focused_review_is_single_character=lambda _word: False,
        _candidate_for_entry_from_list=lambda *a, **k: None,
        _candidate_word_for_ocr_source=lambda *a: "",
        _review_similarity_key=lambda value: value,
        replace=lambda value: value,
    )

    workflow.run_focused_filter(review, deps)
    assert len(calls) == 1

    # First chunk scans page 001 (no hit) and page 002 (one hit).
    _key1, worker1, done1, _failed1 = calls[0]
    done1(worker1())
    assert len(calls) == 2
    assert len(review.filtered_targets) == 1
    assert all(target["page_index"] != 0 for target in review.filtered_targets)

    # Scan-time attestations plus one bounded recheck per intermediate chunk
    # and one complete-prefix recheck at the terminal. Rehashing the whole
    # prefix at every chunk grows quadratically with the page count.
    assert len(verify_calls) <= 11

    # Second chunk scans page 003 and schedules a final chunk for page 004.
    _key2, worker2, done2, _failed2 = calls[1]
    done2(worker2())
    assert len(calls) == 3

    # Mutate the already-scanned no-hit page after its own scan returned,
    # but before the overall epoch can publish its terminal completion.
    if mutation == "pdic":
        pdic_paths[pages[0]].write_bytes(b"pdic-001-after")
    elif mutation == "ocr":
        ocr_paths[pages[0]].write_text(
            '{"review_candidates": [{"changed": true}]}', encoding="utf-8",
        )
    else:
        section_paths[pages[0]].write_bytes(b"section-001-after")

    _key3, worker3, done3, _failed3 = calls[2]
    done3(worker3())

    assert review._filter_scan_failed is True
    assert review._filter_scan_complete is False
    assert all(target["page_index"] != 0 for target in review.filtered_targets)
