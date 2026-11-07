"""R4.2 next hardening: no settings side effects on rejected scan / source race.

All data here are generated fixtures. No real scans or operator acceptance.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.io.formats import write_pdic
from picture_capture.models import Entry
from picture_capture.proofreading.review_risk_witness_storage import (
    publish_review_risk_witnesses, review_risk_witness_path,
)
from picture_capture.proofreading import review_risk_snapshot
from picture_capture.ui import focused_filter_workflow as owner


class Var:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


def _review_for_settings():
    settings = SimpleNamespace(
        focused_review_include_ocr_mismatch=False,
        focused_review_include_characters=False,
        focused_review_exclude_single_character=False,
        focused_review_exclude_reference_words=False,
        focused_review_characters="KEEP",
        focused_review_batch_size=20,
        focused_review_risk_queue_enabled=False,
        focused_review_risk_witness_capture=False,
        focused_review_timing_enabled=False,
    )
    saved = []
    parent = SimpleNamespace(
        settings=settings, save_settings=lambda: saved.append(True),
    )
    review = SimpleNamespace(
        parent=parent,
        focused_include_mismatch_var=Var(True),
        focused_include_characters_var=Var(True),
        focused_exclude_single_var=Var(True),
        focused_exclude_reference_var=Var(True),
        focused_characters_var=Var("NEW"),
        focused_batch_size_var=Var("invalid"),
        focused_risk_priority_var=Var(True),
        focused_risk_capture_var=Var(True),
        focused_timing_var=Var(True),
    )
    return review, settings, saved


def test_invalid_batch_size_changes_no_settings_or_checkbox_state():
    review, settings, saved = _review_for_settings()
    before = dict(vars(settings))
    with pytest.raises(ValueError, match="整数"):
        owner._persist_focused_filter_settings(review, SimpleNamespace())
    assert vars(settings) == before
    assert review.focused_batch_size_var.get() == "invalid"
    assert not saved


def _guard_review(*, active=True, saving=False, pending=True, include_chars=False):
    review, settings, saved = _review_for_settings()
    parsed, persisted, statuses, messages = [], [], [], []
    review._filter_rows_active = active
    review._filter_save_running = saving
    review._filter_pending_changes = ({0: {(9, 10): {"new_word": "manual"}}} if pending else {})
    review.focused_page_range_var = Var("1")
    review.focused_include_characters_var = Var(include_chars)
    review.focused_characters_var = Var("")
    review.parent.project = SimpleNamespace(root=Path("/tmp/synthetic"), images=[])
    review.parent._parse_page_spec = lambda spec: parsed.append(spec) or []
    review.parent.status_var = SimpleNamespace(set=statuses.append)
    review._persist_focused_filter_settings = lambda: persisted.append("persist")
    deps = SimpleNamespace(
        messagebox=SimpleNamespace(
            showerror=lambda *a, **kw: messages.append(("error", a)),
            showinfo=lambda *a, **kw: messages.append(("info", a)),
        ),
        _focused_review_character_tokens=lambda _: [],
        # The physical owner resolves live dependencies before rejecting a
        # scan. Supply the full set, so this test observes the real guard.
        read_pdic=lambda *args: [],
        pdic_path=lambda *args: None,
        ocr_cache_root=lambda *args: None,
        json=json,
        _focused_review_is_single_character=lambda *args: False,
        _candidate_for_entry_from_list=lambda *args, **kw: None,
        _candidate_word_for_ocr_source=lambda *args: "",
        _review_similarity_key=lambda value: value,
    )
    return review, deps, parsed, persisted, statuses, messages


@pytest.mark.parametrize("saving,pending", [(False, True), (True, False), (True, True)])
def test_dirty_or_inflight_edit_blocks_before_any_parse_or_setting_write(saving, pending):
    review, deps, parsed, persisted, statuses, messages = _guard_review(
        saving=saving, pending=pending,
    )
    owner.run_focused_filter(review, deps)
    assert parsed == [] and persisted == [] and not messages
    assert statuses and "保存" in statuses[-1]


def test_empty_required_character_filter_does_not_persist_setting():
    review, deps, parsed, persisted, statuses, messages = _guard_review(
        active=False, saving=False, pending=False, include_chars=True,
    )
    owner.run_focused_filter(review, deps)
    assert parsed == ["1"] and persisted == []
    assert len(messages) == 1 and messages[0][0] == "info"


def _attested_page(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    page = project / "001.png"
    Image.new("RGB", (160, 180), "white").save(page)
    cache = project / "QT" / "PaddleOCR" / "001.json"
    cache.parent.mkdir(parents=True)
    pdic = project / "001.pdic"
    coords = [(30, 40), (30, 70)]
    candidates = [
        {
            "candidate_id": f"c{i}", "word": f"word{i}",
            "source_x": x, "source_y": y,
            "selected": True, "coordinate_space": "source_image_pixels",
            "position_variant": "refined", "final_engine": "paddle",
            "decision_reason": "dual_agree_higher_quality",
            "needs_review": i == 1,
            "issue_types": ["OCR_CONFLICT"] if i == 1 else [],
            "paddle": {"accepted": True, "lemma": f"word{i}", "confidence": .98},
            "tesseract": {"accepted": True, "lemma": f"word{i}", "confidence": .98},
        } for i, (x, y) in enumerate(coords)
    ]
    cache.write_text(json.dumps({"review_candidates": candidates}), encoding="utf-8")
    write_pdic(
        pdic, [Entry(word=f"word{i}", x=x, y=y) for i, (x, y) in enumerate(coords)],
        160, ("001", "@", "@"),
    )
    targets = [
        {"page_index": 0, "page_name": page.name, "x": x, "y": y,
         "original_word": f"word{i}", "current_word": f"word{i}",
         "reasons": ("synthetic",)}
        for i, (x, y) in enumerate(coords)
    ]
    assert publish_review_risk_witnesses(
        project_root=project, page=page, cache_path=cache, pdic_path=pdic,
    ) == 2
    return project, page, cache, pdic, targets


def test_changed_origin_sidecar_during_snapshot_invalidates_whole_page(monkeypatch, tmp_path):
    project, page, cache, pdic, targets = _attested_page(tmp_path)
    origin = review_risk_witness_path(cache)
    old_bytes = origin.read_bytes()
    real_read_pdic = review_risk_snapshot.read_pdic
    changes = []
    def injected(path):
        if not changes:
            origin.write_bytes(old_bytes + b" ")
            changes.append(True)
        return real_read_pdic(path)
    monkeypatch.setattr(review_risk_snapshot, "read_pdic", injected)
    result = review_risk_snapshot.prioritized_focused_page_targets(
        targets, project_root=project, page=page,
        cache_path=cache, pdic_path=pdic, enabled=True,
    )
    assert changes == [True]
    assert [row["original_word"] for row in result] == ["word0", "word1"]
    assert all(row is old for row, old in zip(result, targets))
    assert origin.read_bytes() == old_bytes + b" "


def test_unready_native_source_refuses_before_settings_or_save():
    review, deps, parsed, persisted, statuses, messages = _guard_review(
        active=False, saving=False, pending=False,
    )
    review.focused_characters_var.set("valid")
    deps._focused_review_character_tokens = lambda text: [text]
    review.parent.current_page = Path("/tmp/synthetic/001.png")
    review._rendered_page_stem = ""
    review.focused_batch_size_var = Var("20")
    saves = []
    review.save = lambda **kw: saves.append(kw) or True
    owner.run_focused_filter(review, deps)
    assert parsed == ["1"] and persisted == [] and saves == []
    assert "加载" in statuses[-1]


def test_failing_r3_guarded_save_refuses_without_persisting_filter_settings():
    review, deps, parsed, persisted, statuses, messages = _guard_review(
        active=False, saving=False, pending=False,
    )
    review.focused_characters_var.set("valid")
    deps._focused_review_character_tokens = lambda text: [text]
    review.parent.current_page = Path("/tmp/synthetic/001.png")
    review._rendered_page_stem = "001"
    review.focused_batch_size_var = Var("20")
    review.save = lambda **kw: (_ for _ in ()).throw(
        RuntimeError("synthetic blocked R3 source")
    )
    owner.run_focused_filter(review, deps)
    assert parsed == ["1"] and persisted == []
    assert "保存失败" in statuses[-1]


def test_refused_r3_false_save_is_not_treated_as_success():
    review, deps, parsed, persisted, statuses, messages = _guard_review(
        active=False, saving=False, pending=False,
    )
    review.focused_characters_var.set("valid")
    deps._focused_review_character_tokens = lambda text: [text]
    review.parent.current_page = Path("/tmp/synthetic/001.png")
    review._rendered_page_stem = "001"
    review.focused_batch_size_var = Var("20")
    review.save = lambda **kw: False
    owner.run_focused_filter(review, deps)
    assert parsed == ["1"] and persisted == []
    assert "未保存" in statuses[-1]
