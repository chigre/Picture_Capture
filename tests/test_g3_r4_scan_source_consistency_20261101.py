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


@pytest.mark.parametrize("replacement", ("project_root", "image_selection"))
def test_scan_terminal_rejects_replaced_project_session(tmp_path, replacement):
    """An old ReviewWindow scan must not publish after the main app switches projects.

    ProjectSessionWorkflow updates parent.project while ReviewWindow is a
    separate non-modal Toplevel. Captured old source files can remain byte
    identical, so checking only those old files is not proof that this scan
    still belongs to the active project session.
    """
    review, _deps, call, status, indicator, *_ = _fixture(tmp_path)
    _key, worker, done, _failed = call
    payload = worker()

    if replacement == "project_root":
        new_root = tmp_path / "replacement-project"
        new_root.mkdir()
        new_page = new_root / "001.png"
        Image.new("RGB", (8, 8), "black").save(new_page)
        review.parent.project = SimpleNamespace(root=new_root, images=[new_page])
    else:
        new_page = tmp_path / "002.png"
        Image.new("RGB", (8, 8), "black").save(new_page)
        review.parent.project = SimpleNamespace(root=tmp_path, images=[new_page])

    # The old scan's source bytes remain unchanged. Only the active project
    # root or selected page list has changed before its Tk terminal arrives.
    done(payload)

    assert review.filtered_targets == [], (
        "a completed old-project scan published rows into the new project session"
    )
    assert review._filter_scan_complete is False
    assert review._filter_scan_failed is True
    assert "失败" in status.get() or "不完整" in status.get()
    assert "PRIVATE" not in repr((status.get(), indicator.get()))

@pytest.mark.parametrize("mutation", ("pdic", "ocr", "section"))
def test_completed_scan_rejects_later_no_hit_page_source_drift(tmp_path, mutation):
    review, deps, _initial_call, status, _indicator, pdic, cache, section = _fixture(tmp_path)
    no_hit = tmp_path / "000-no-hit.png"
    Image.new("RGB", (8, 8), "white").save(no_hit)
    no_hit_pdic = no_hit.with_suffix(".pdic")
    no_hit_pdic.write_bytes(b"synthetic-no-hit-pdic")
    no_hit_cache = cache.parent / "000-no-hit.json"
    no_hit_cache.write_text('{"review_candidates": []}', encoding="utf-8")
    no_hit_section = page_sections_read_path_for_image(no_hit)
    no_hit_section.parent.mkdir(parents=True, exist_ok=True)
    no_hit_section.write_bytes(b"synthetic-no-hit-section")

    original_page = review.parent.project.images[0]
    review.parent.project.images = [no_hit, original_page]
    review.parent.current_page = no_hit
    review.parent._parse_page_spec = lambda _value: [0, 1]
    review.focused_page_range_var.set("1-2")
    review._focused_batch_size = lambda: 1
    review._filter_available_target_count = lambda: len(review.filtered_targets)
    pdic_by_page = {no_hit: no_hit_pdic, original_page: pdic}
    deps.pdic_path = lambda page: pdic_by_page[page]
    original_read = deps.read_pdic
    deps.read_pdic = lambda path: [] if path == no_hit_pdic else original_read(path)

    # Re-run only after installing the two-page project; _fixture() already
    # starts its own one-page scan before returning.
    calls = []
    review.parent._start_ui_worker = lambda *args: calls.append(args) or len(calls)
    workflow.run_focused_filter(review, deps)
    assert len(calls) == 1

    # First (no-hit) page and second (hit) page complete in the initial scan.
    _key, worker, done, failed = calls[0]
    done(worker())
    assert review._filter_scan_complete is True
    assert len(review.filtered_targets) == 1
    assert review.filtered_targets[0]["page_index"] == 1

    # A new entry appears on the previously no-hit page after terminal
    # completion. A subsequent render/navigation request must not continue
    # presenting the old scan as a complete result.
    no_hit_pdic.write_bytes(b"synthetic-no-hit-pdic-now-has-entry")
    review._filter_batch_snapshot = lambda _index: None
    workflow._request_filter_batch_render(review, deps)
    assert review._filter_scan_failed is True
    assert review._filter_scan_complete is False
    assert "来源" in status.get() or "重新筛选" in status.get()

def test_inflight_crop_payload_cannot_publish_after_no_hit_epoch_source_drift(tmp_path):
    review, deps, _initial_call, _status, _indicator, pdic, cache, _section = _fixture(tmp_path)
    no_hit = tmp_path / "000-no-hit.png"
    Image.new("RGB", (8, 8), "white").save(no_hit)
    no_hit_pdic = no_hit.with_suffix(".pdic")
    no_hit_pdic.write_bytes(b"synthetic-no-hit-pdic")
    no_hit_cache = cache.parent / "000-no-hit.json"
    no_hit_cache.write_text('{"review_candidates": []}', encoding="utf-8")
    no_hit_section = page_sections_read_path_for_image(no_hit)
    no_hit_section.parent.mkdir(parents=True, exist_ok=True)
    no_hit_section.write_bytes(b"synthetic-no-hit-section")

    original_page = review.parent.project.images[0]
    review.parent.project.images = [no_hit, original_page]
    review.parent.current_page = no_hit
    review.parent._parse_page_spec = lambda _value: [0, 1]
    review.focused_page_range_var.set("1-2")
    review._focused_batch_size = lambda: 1
    pdic_by_page = {no_hit: no_hit_pdic, original_page: pdic}
    deps.pdic_path = lambda page: pdic_by_page[page]
    original_read = deps.read_pdic
    deps.read_pdic = lambda path: [] if path == no_hit_pdic else original_read(path)
    calls = []
    review.parent._start_ui_worker = lambda *args: calls.append(args) or len(calls)
    workflow.run_focused_filter(review, deps)
    _key, scan_worker, scan_done, _scan_failed = calls[0]
    scan_done(scan_worker())
    assert review._filter_scan_complete is True
    target = review.filtered_targets[0]
    assert target["page_index"] == 1

    pages = [no_hit, original_page]
    crop_witness = workflow.focused_crop_source_witness(pages, [target])
    cache_key = (0, ("synthetic-render-settings", crop_witness))
    review._filter_batch_snapshot = lambda _index: (
        cache_key, [dict(target)], pages, None, 300, 300, 1.0, False,
    )
    review.review_zoom_auto = False
    review._render_filter_batch = lambda *_args: rendered.append(True)
    review._reset_rows_scroll_top = lambda: None
    review._schedule_filter_next_batch_preload = lambda: None
    review._update_filter_batch_indicator = lambda: None
    rendered = []
    deps._format_layout_percent = lambda value: str(value)

    # The batch snapshot is valid when the crop payload is accepted, but a
    # no-hit page changes while that payload is in flight.
    no_hit_section.write_bytes(b"synthetic-no-hit-section-after-terminal")
    applied = workflow._apply_filter_batch_payload(
        review, deps, 0, cache_key, ([object()], 1.0, [(1, 1)]),
    )
    assert applied is False
    assert rendered == []
    assert review._filter_scan_failed is True
    assert review._filter_scan_complete is False

@pytest.mark.parametrize(
    ("uncertain_pages", "launch_failed"),
    [({0}, False), (set(), True)],
)
def test_refilter_refuses_unresolved_save_even_with_empty_edit_queue(
    tmp_path, uncertain_pages, launch_failed,
):
    """An empty debounce queue does not prove an ambiguous PDIC write settled."""
    review, deps, call, status, _indicator, _pdic, _cache, _section = _fixture(
        tmp_path,
    )
    _key, worker, done, _failed = call
    done(worker())
    assert review._filter_scan_complete is True
    assert len(review.filtered_targets) == 1

    previous_serial = review._filter_scan_serial
    previous_targets = list(review.filtered_targets)
    previous_witness = review.filtered_targets[0]["_focused_scan_source_witness"]
    review._filter_save_uncertain_pages = set(uncertain_pages)
    review._filter_save_launch_failed = launch_failed
    review._filter_pending_changes = {}
    launches = []
    review.parent._start_ui_worker = (
        lambda *args: launches.append(args) or len(launches)
    )

    workflow.run_focused_filter(review, deps)

    assert launches == [], "unsettled write must not start a replacement scan"
    assert review._filter_scan_serial == previous_serial
    assert review._filter_scan_complete is True
    assert review.filtered_targets == previous_targets
    assert (
        review.filtered_targets[0]["_focused_scan_source_witness"]
        == previous_witness
    )
    assert "核对" in status.get()

    # A separately settled writer may clear the flags; rescan must remain
    # available rather than being permanently disabled by the guard.
    review._filter_save_uncertain_pages = set()
    review._filter_save_launch_failed = False
    workflow.run_focused_filter(review, deps)
    assert len(launches) == 1
    assert review._filter_scan_serial == previous_serial + 1
