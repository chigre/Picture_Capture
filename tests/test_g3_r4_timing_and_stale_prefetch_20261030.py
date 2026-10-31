"""G3 R4.2 opt-in aggregate duration and stale prefetch epoch safety.

Synthetic-only tests. Timing is operational local data, not a measured speedup.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.models import AppSettings
from picture_capture.proofreading.review_timing import ReviewTimingSession
from picture_capture.proofreading.focused_crop_source_fingerprint import (
    focused_crop_source_witness,
)
from picture_capture.ui import focused_filter_workflow as workflow


def test_legacy_settings_have_aggregate_timing_disabled():
    assert AppSettings().focused_review_timing_enabled is False


def test_timing_rejects_invalid_epoch_stage_and_non_numeric_elapsed():
    timing = ReviewTimingSession(epoch=7)
    assert timing.add("scan", 1.25, 2, epoch=7)
    assert timing.add("risk", .15, 1, epoch=7)
    assert timing.add("crop", .20, 1, epoch=7)
    assert timing.add("save", .10, 3, epoch=7)
    assert not timing.add("scan", 900, 99, epoch=6)
    for stage, elapsed, count in [
        ("candidate_word", .1, 1), ("scan", float("nan"), 1),
        ("scan", float("inf"), 1), ("scan", -1, 1),
        ("scan", True, 1), ("scan", .1, -1), ("scan", .1, True),
    ]:
        assert not timing.add(stage, elapsed, count, epoch=7)
    result = timing.snapshot()
    assert result["format"] == "focused-review-local-aggregate-v1"
    assert result["scope"] == "volatile-local-memory"
    assert result["stages"]["scan"] == {"seconds": 1.25, "count": 2}
    assert result["stages"]["risk"] == {"seconds": .15, "count": 1}
    assert result["stages"]["crop"] == {"seconds": .2, "count": 1}
    assert result["stages"]["save"] == {"seconds": .1, "count": 3}
    assert all(isinstance(x, (int, float, dict, str)) for x in result.values())
    serialized = json.dumps(result, ensure_ascii=False)
    for key in ("page_name", "word", "source_x", "OCR", "original_word"):
        assert key not in serialized


def test_timing_labels_do_not_claim_human_review_speedup_or_sum_subset():
    timing = ReviewTimingSession(epoch=1)
    assert "风险校验" in timing.label
    assert "扫描" in timing.label
    assert "非人工校对耗时" in timing.label
    timing.add("scan", .4, 2, epoch=1)
    timing.add("risk", .1, 2, epoch=1)
    assert "0.400" in timing.label
    assert "0.100" in timing.label


def test_legacy_missing_new_tk_timing_variable_keeps_default_off():
    class Var:
        def __init__(self, x): self.x = x
        def get(self): return self.x
        def set(self, x): self.x = x
    settings = SimpleNamespace()
    saved = []
    review = SimpleNamespace(
        parent=SimpleNamespace(settings=settings, save_settings=lambda: saved.append(1)),
        focused_include_mismatch_var=Var(True),
        focused_include_characters_var=Var(False),
        focused_exclude_single_var=Var(False),
        focused_exclude_reference_var=Var(False),
        focused_characters_var=Var("a"),
        focused_batch_size_var=Var("20"),
    )
    workflow._persist_focused_filter_settings(review, SimpleNamespace())
    assert settings.focused_review_timing_enabled is False
    assert len(saved) == 1
    review.focused_timing_var = Var(True)
    workflow._persist_focused_filter_settings(review, SimpleNamespace())
    assert settings.focused_review_timing_enabled is True
    assert len(saved) == 2


def _fake_prefetch():
    callbacks, cache_calls, apply_calls = [], [], []
    # Use the actual content witness contract even for the empty synthetic
    # page/target list. A bare "sig" is not a valid source-bound cache key.
    source_witness = focused_crop_source_witness([], [])
    worker = SimpleNamespace(
        _filter_rows_active=True,
        filtered_batch_index=0,
        _filter_scan_serial=8,
        _filter_batch_render_cache={},
        _filter_prefetch_key=None,
        _focused_timing_session=None,
        _filter_batch_snapshot=lambda index: ((index, ("sig", source_witness)), [], [],
                                              None, 10, 240, 1.0, False),
        _cache_filter_batch_payload=lambda *args: cache_calls.append(args),
        _apply_filter_batch_payload=lambda *args: apply_calls.append(args),
        parent=SimpleNamespace(
            _start_ui_worker=lambda *args: callbacks.append(args),
        ),
    )
    deps = SimpleNamespace(
        ReviewWindow=SimpleNamespace(
            _prepare_filter_batch_payload=lambda *args: ([], 1.0, []),
        ),
    )
    return worker, deps, callbacks, cache_calls, apply_calls


def test_stale_prefetch_after_restart_cannot_populate_cache_or_new_epoch():
    review, deps, workers, cached, applied = _fake_prefetch()
    workflow._schedule_filter_next_batch_preload(review, deps)
    assert len(workers) == 1
    key, job, done, failed = workers[0]
    assert key.startswith("focused-filter-prefetch-")
    # New scan starts with same future batch cache signature but distinct epoch.
    captured_key = review._filter_prefetch_key
    review._filter_scan_serial += 1
    review._filter_prefetch_key = captured_key
    done(job())
    assert cached == [] and applied == []
    # Late failure must not reset the *new* scan's prefetch key.
    failed(OSError("old failure"), "old traceback")
    assert review._filter_prefetch_key == captured_key


def test_prefetch_for_current_epoch_still_delivers_once():
    review, deps, workers, cached, applied = _fake_prefetch()
    workflow._schedule_filter_next_batch_preload(review, deps)
    key, job, done, failed = workers[0]
    captured_key = review._filter_prefetch_key
    done(job())
    assert len(cached) == 1 and cached[0][0] == captured_key
    assert applied == []
    assert review._filter_prefetch_key is None


def test_focused_ui_wires_opt_in_timing_and_rest_guard_without_default_side_effects():
    base = Path(__file__).resolve().parents[1] / "src/picture_capture"
    scan = (base / "ui/focused_filter_workflow.py").read_text("utf-8")
    init = (base / "ui/review_window_initialization.py").read_text("utf-8")
    view = (base / "ui/review_workspace_workflow.py").read_text("utf-8")
    assert "focused_review_timing_enabled" in scan
    assert "focused_timing_var" in init and "focused_timing_var" in view
    assert "ReviewTimingSession" in scan
    assert "perf_counter" in scan
    assert "focused-filter-scan-" in scan
    assert "self._filter_scan_serial" in scan
    assert "serial != self._filter_scan_serial" in scan
    assert "self._filter_render_serial += 1" in scan
    assert "self.parent._invalidate_ui_worker" in scan
