"""G3 R4.2: async filter scans must remain bound to their PDIC/OCR/SECTION bytes.

All fixtures are disposable synthetic files. No real dictionary/OCR data.
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
        self.writes = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        self.writes.append(value)


def _fixture(tmp_path: Path, mutation: str | None = None):
    pages = [tmp_path / "001.png"]
    page = pages[0]
    Image.new("RGB", (8, 8), "white").save(page)
    pdic = page.with_suffix(".pdic")
    pdic.write_bytes(b"synthetic-pdic-before")
    ocr_root = tmp_path / "ocr-cache"
    ocr_root.mkdir()
    cache = ocr_root / "001.json"
    cache.write_text('{"review_candidates": []}', encoding="utf-8")
    section = page_sections_read_path_for_image(page)
    section.parent.mkdir(parents=True, exist_ok=True)
    section.write_bytes(b"synthetic-section-before")

    calls = []
    status, indicator = _Var(""), _Var("")
    def read_pdic(path):
        if mutation == "pdic":
            path.write_bytes(b"synthetic-pdic-after")
        elif mutation == "section":
            section.write_bytes(b"synthetic-section-after")
        return [SimpleNamespace(word="fixture", x=13, y=27)]

    class _Json:
        @staticmethod
        def loads(payload):
            value = json.loads(payload)
            if mutation == "ocr":
                cache.write_text('{"review_candidates": [{"changed": true}]}', encoding="utf-8")
            return value

    parent = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path, images=pages),
        current_page=page,
        status_var=status,
        settings=SimpleNamespace(character_height=18),
        canvas=SimpleNamespace(winfo_width=lambda: 320),
        _project_words=[],
        _parse_page_spec=lambda _value: [0],
        _invalidate_ui_worker=lambda _key: None,
        _start_ui_worker=lambda *args: calls.append(args),
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
        focused_page_range_var=_Var("1"),
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
        messagebox=SimpleNamespace(showerror=lambda *a, **k: None),
        _focused_review_character_tokens=lambda _value: (),
        read_pdic=read_pdic,
        pdic_path=lambda _page: pdic,
        ocr_cache_root=lambda _root: ocr_root,
        json=_Json,
        _focused_review_is_single_character=lambda _word: False,
        _candidate_for_entry_from_list=lambda *a, **k: None,
        _candidate_word_for_ocr_source=lambda *a: "",
        _review_similarity_key=lambda value: value,
        replace=lambda value: value,
    )
    workflow.run_focused_filter(review, deps)
    assert len(calls) == 1
    return review, deps, calls[0], status, indicator, pdic, cache, section


@pytest.mark.parametrize("mutation", ("pdic", "ocr", "section"))
def test_scan_refuses_source_bytes_changed_during_page_read(tmp_path, mutation):
    review, _deps, call, _status, _indicator, _pdic, _cache, _section = _fixture(
        tmp_path, mutation,
    )
    _key, worker, _done, failed = call
    with pytest.raises((RuntimeError, ValueError), match="source|来源|变化"):
        worker()
    failed(OSError("PRIVATE_SYNTHETIC_SOURCE_PATH"), "PRIVATE_TRACE")
    assert review.filtered_targets == []
    assert review._filter_scan_complete is False
    assert review._filter_scan_failed is True


def test_scan_targets_carry_source_witness_and_reject_later_ocr_cache_drift(tmp_path):
    review, deps, call, _status, _indicator, _pdic, cache, _section = _fixture(tmp_path)
    _key, worker, done, _failed = call
    done(worker())
    assert len(review.filtered_targets) == 1
    target = review.filtered_targets[0]
    assert target.get("_focused_scan_source_witness") is not None

    # A same-length cache replacement with a restored timestamp must not
    # authorize rendering a result derived from the old OCR candidates.
    original_stat = cache.stat()
    cache.write_text('{"review_candidates":[] }', encoding="utf-8")
    import os
    os.utime(cache, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    snapshot = workflow._filter_batch_snapshot(review, deps, 0)
    assert snapshot is None
