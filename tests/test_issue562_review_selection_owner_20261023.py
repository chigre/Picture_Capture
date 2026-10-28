"""Physical owner and persistence contracts for OCR review selection (#562)."""
from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture import app as shell
from picture_capture.models import Entry as WordEntry
from picture_capture.ui import review_selection_workflow as selection

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
NAMES = [
    "_paddle_cache_path",
    "_manual_selection_path",
    "_read_manual_overrides",
    "_flush_pending_manual_override",
    "_write_manual_override",
    "_queue_proofreading_add_evidence",
    "_flush_proofreading_add_evidence",
    "_queue_proofreading_candidate_evidence",
    "_flush_proofreading_candidate_evidence",
    "_schedule_deferred_page_save",
    "set_candidate_selected",
    "apply_candidate_choice",
    "candidate_checkbox_changed",
    "_scroll_review_entry_into_view",
    "open_ocr_conflict_review",
    "_current_page_quality_text",
    "_restore_entry_ocr_metadata"
]


def test_owner_functions_native_signatures_and_calltime_dependencies(monkeypatch):
    app_tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    klass = next(n for n in app_tree.body if isinstance(n, ast.ClassDef)
                 and n.name == "PictureCaptureApp")
    wrappers = {n.name: n for n in klass.body if isinstance(n, ast.FunctionDef)}
    owner_ast = ast.parse((ROOT / "ui/review_selection_workflow.py").read_text(encoding="utf-8"))
    owned = {n.name for n in owner_ast.body if isinstance(n, ast.FunctionDef)}
    assert set(NAMES) <= owned
    for name in NAMES:
        assert name in wrappers
        calls = [n for n in ast.walk(wrappers[name]) if isinstance(n, ast.Call)]
        assert any(isinstance(n.func, ast.Attribute) and n.func.attr == name
                   and isinstance(n.func.value, ast.Name)
                   and n.func.value.id == "_review_selection" for n in calls)
        assert any(isinstance(n.func, ast.Name)
                   and n.func.id == "_review_selection_deps" for n in calls)
        assert list(inspect.signature(getattr(shell.PictureCaptureApp, name)).parameters)[0] == "self"
    assert not any(isinstance(n, ast.ImportFrom)
                   and n.module in {"app", "picture_capture.app"}
                   for n in ast.walk(owner_ast))
    assert inspect.signature(shell.PictureCaptureApp._write_manual_override).parameters["defer"].kind is inspect.Parameter.KEYWORD_ONLY
    assert inspect.signature(shell.PictureCaptureApp._schedule_deferred_page_save).parameters["sync_editors"].kind is inspect.Parameter.KEYWORD_ONLY
    marker = object()
    monkeypatch.setattr(shell, "read_pdic", marker)
    monkeypatch.setattr(shell, "ocr_cache_root", marker)
    assert shell._review_selection_deps().read_pdic is marker
    assert shell._review_selection_deps().ocr_cache_root is marker


def test_pending_manual_override_flush_is_page_scoped_and_disk_reads_are_safe(tmp_path):
    path_a = tmp_path / "a_manual_selection.json"
    path_b = tmp_path / "b_manual_selection.json"
    current = [path_a]
    view = SimpleNamespace(
        current_page=SimpleNamespace(stem="a"),
        _pending_manual_override_path=None,
        _pending_manual_override_payload=None,
    )
    deps = SimpleNamespace(json=json)
    view._manual_selection_path = lambda: current[0]
    view._read_manual_overrides = lambda: selection._read_manual_overrides(view, deps)
    view._flush_pending_manual_override = lambda: selection._flush_pending_manual_override(view, deps)
    cand_a = {"candidate_id": "one", "word": "a"}
    selection._write_manual_override(view, deps, cand_a, selected=True, defer=True)
    assert not path_a.exists()
    assert view._read_manual_overrides()["overrides"]["one"]["selected"] is True
    current[0] = path_b
    view.current_page = SimpleNamespace(stem="b")
    selection._write_manual_override(view, deps, {"candidate_id":"two","word":"b"}, selected=False, defer=True)
    assert json.loads(path_a.read_text(encoding="utf-8"))["overrides"]["one"]["selected"] is True
    assert not path_b.exists()
    view._flush_pending_manual_override()
    assert json.loads(path_b.read_text(encoding="utf-8"))["page"] == "b"
    path_b.write_text("not json", encoding="utf-8")
    # A malformed human sidecar cannot authorize an empty rewrite.
    with pytest.raises(RuntimeError, match="损坏"):
        view._read_manual_overrides()
    assert path_b.read_bytes() == b"not json"


def test_selection_changes_local_model_before_deferred_persistence():
    event = []
    candidate = {"candidate_id":"cid", "word":"apple", "source_x":4, "source_y":8}
    view = SimpleNamespace(
        entries=[], ocr_review_candidates=[candidate], candidate_check_vars={},
        status_var=SimpleNamespace(set=lambda text: event.append(("status", text))),
    )
    view._claim_page_for_manual_edit = lambda: True
    view._queue_proofreading_candidate_evidence = lambda *args: event.append(("queue", None))
    view._sync_entry_editor_texts = lambda: event.append(("sync", None))
    view._entry_for_candidate = lambda cand: next(
        (e for e in view.entries if e.candidate_id == cand["candidate_id"]), None)
    view._sort_entries_reading_order = lambda: view.entries.sort(key=lambda e: e.y)
    view._write_manual_override = lambda *args, **kw: event.append(("override", kw))
    view._update_entry_overlays_local = lambda **kw: event.append(("overlay", kw))
    view._schedule_deferred_page_save = lambda **kw: event.append(("schedule", kw))
    deps = SimpleNamespace(WordEntry=WordEntry)
    assert selection.set_candidate_selected(view, deps, candidate, True) is True
    assert len(view.entries) == 1 and view.entries[0].candidate_id == "cid"
    assert [row[0] for row in event[:4]] == ["queue", "sync", "override", "overlay"]
    assert any(row[0] == "schedule" and row[1] == {"sync_editors": False} for row in event)
    event.clear()
    assert selection.set_candidate_selected(view, deps, candidate, False) is True
    assert not view.entries
    assert [row[0] for row in event[:4]] == ["queue", "sync", "override", "overlay"]


def test_deferred_save_replaces_pending_timer_without_writing(monkeypatch, tmp_path):
    from dataclasses import replace
    cancelled, jobs = [], []
    page = tmp_path / "page.png"
    page.write_bytes(b"synthetic page; not a real dictionary scan")
    pdic = tmp_path / "page.PDIC"
    pdic.write_bytes(b"original human PDIC bytes")
    view = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path),
        current_page=page, image=SimpleNamespace(width=200),
        entries=[WordEntry(word="a", x=2, y=3)],
        current_index=0, _deferred_save_job="old",
        _deferred_save_delay_ms=120,
        pages_tuple=lambda: ("page", "@", "@"),
        after_cancel=lambda token: cancelled.append(token),
        after=lambda delay, callback: jobs.append((delay, callback)) or "new",
        _flush_deferred_page_save=lambda: None,
    )
    selection._schedule_deferred_page_save(
        view, SimpleNamespace(tk=SimpleNamespace(TclError=RuntimeError), replace=replace,
                        pdic_path=lambda _page: pdic),
        sync_editors=False,
    )
    assert cancelled == ["old"] and jobs == [(120, view._flush_deferred_page_save)]
    assert view._deferred_save_job == "new"
    assert view._deferred_save_page == page
    assert view._deferred_save_snapshot[0] == page
    assert view._deferred_save_pdic_origin == (page, b"original human PDIC bytes")
    assert pdic.read_bytes() == b"original human PDIC bytes"
    assert view._deferred_save_snapshot[1][0] is not view.entries[0]
