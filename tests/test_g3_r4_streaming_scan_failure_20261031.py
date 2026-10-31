"""R4.2 synthetic streaming failures must not look like a running or complete scan.

No real dictionary pages, OCR cache, human evidence or persistence writes.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.ui import focused_filter_workflow as workflow


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _stream_fixture(tmp_path):
    pages = [tmp_path / "001.png", tmp_path / "002.png"]
    calls, workspace = [], []
    status, indicator = Var(""), Var("")
    parent = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path, images=pages),
        current_page=pages[0],
        status_var=status,
        settings=SimpleNamespace(character_height=18),
        _project_words=[],
        _parse_page_spec=lambda _: [0, 1],
        _invalidate_ui_worker=lambda _: None,
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
        review_mode_var=Var("filter"),
        filter_batch_var=indicator,
        focused_page_range_var=Var("1-2"),
        focused_include_mismatch_var=Var(False),
        focused_include_characters_var=Var(False),
        focused_exclude_single_var=Var(False),
        focused_exclude_reference_var=Var(False),
        focused_risk_priority_var=Var(False),
        focused_timing_var=Var(False),
        focused_characters_var=Var(""),
        focused_batch_size_var=Var("1"),
        review_ocr_compare_var=Var("fusion"),
        OCR_COMPARE_LABEL_TO_KEY={"fusion": "fusion"},
        _persist_focused_filter_settings=lambda: None,
        _set_filter_navigation=lambda enabled: None,
        _focused_batch_size=lambda: 1,
        _clear_review_workspace=lambda message: workspace.append(message),
        _update_title=lambda: None,
        _update_filter_batch_indicator=lambda: None,
        _request_filter_batch_render=lambda: None,
        _schedule_filter_next_batch_preload=lambda: None,
    )
    def read_pdic(path):
        if path.stem == "002":
            raise OSError("PRIVATE_PATH_DO_NOT_EXPOSE")
        return [SimpleNamespace(word="fixture", x=13, y=27)]

    deps = SimpleNamespace(
        messagebox=SimpleNamespace(showerror=lambda *a, **kw: None),
        _focused_review_character_tokens=lambda _: (),
        read_pdic=read_pdic,
        pdic_path=lambda page: page.with_suffix(".pdic"),
        ocr_cache_root=lambda root: root / "unused-ocr-dir",
        json=json,
        _focused_review_is_single_character=lambda _: False,
        _candidate_for_entry_from_list=lambda *a, **kw: None,
        _candidate_word_for_ocr_source=lambda *a: "",
        _review_similarity_key=lambda text: text,
    )
    workflow.run_focused_filter(review, deps)
    assert len(calls) == 1
    first_key, first_worker, first_done, _ = calls[0]
    assert first_key.startswith("focused-filter-scan-")
    first_done(first_worker())
    assert len(calls) == 2
    assert len(review.filtered_targets) == 1
    rest_key, rest_worker, rest_done, rest_failed = calls[1]
    assert rest_key.startswith("focused-filter-scan-rest-")
    with pytest.raises(OSError):
        rest_worker()
    return review, status, indicator, rest_failed, workspace


def test_remainder_error_is_explicitly_terminal_without_losing_first_batch(tmp_path):
    review, status, indicator, failed, workspace = _stream_fixture(tmp_path)
    previous_targets = list(review.filtered_targets)
    previous_workspace = list(workspace)
    failed(OSError("PRIVATE_PATH_DO_NOT_EXPOSE"), "")
    assert review._filter_scan_failed is True
    assert review._filter_scan_complete is False
    assert "失败" in status.get() or "中断" in status.get()
    assert "失败" in indicator.get() or "中断" in indicator.get()
    assert "PRIVATE_PATH_DO_NOT_EXPOSE" not in status.get()
    assert "PRIVATE_PATH_DO_NOT_EXPOSE" not in indicator.get()
    assert review.filtered_targets == previous_targets
    assert workspace == previous_workspace
    assert review._filter_rows_active is True


def test_stale_remainder_failure_cannot_poison_new_epoch(tmp_path):
    review, status, indicator, failed, workspace = _stream_fixture(tmp_path)
    review._filter_scan_serial += 1
    review._filter_scan_failed = False
    status.set("new scan running")
    indicator.set("new batch")
    failed(OSError("stale PRIVATE_PATH_DO_NOT_EXPOSE"), "")
    assert review._filter_scan_failed is False
    assert status.get() == "new scan running"
    assert indicator.get() == "new batch"
