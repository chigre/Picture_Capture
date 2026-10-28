"""G1 candidate checkbox manual_selection source version: synthetic faults only."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from picture_capture.ui import review_selection_workflow as owner


def scene(tmp_path):
    page = SimpleNamespace(stem="page")
    path = tmp_path / "page_manual_selection.json"
    view = SimpleNamespace(
        current_page=page, _pending_manual_override_path=None,
        _pending_manual_override_payload=None, status_var=SimpleNamespace(set=lambda x: None),
    )
    deps = SimpleNamespace(json=json)
    view._manual_selection_path = lambda: path
    view._read_manual_overrides = lambda: owner._read_manual_overrides(view, deps)
    view._flush_pending_manual_override = lambda: owner._flush_pending_manual_override(view, deps)
    view._write_manual_override = lambda *a, **kw: owner._write_manual_override(view, deps, *a, **kw)
    return view, path, deps


@pytest.mark.parametrize("bad", [
    b"not json", b'{"version":1,"overrides":{},"overrides":{}}',
    b'{"version":1,"overrides":{"a":{"selected":NaN}}}',
    b'{"version":1,"page":"other","overrides":{}}',
    b'{"version":2,"page":"page","overrides":{}}',
    b'{"version":1,"page":"page","overrides":[]}',
    b'{"version":true,"page":"page","overrides":{}}',
])
def test_corrupt_or_other_page_human_decisions_never_become_empty_rewrite(tmp_path, bad):
    view, path, deps = scene(tmp_path)
    path.write_bytes(bad)
    with pytest.raises(RuntimeError):
        view._write_manual_override({"candidate_id":"cid","word":"old"}, selected=False, defer=True)
    assert path.read_bytes() == bad
    assert view._pending_manual_override_path is None
    assert view._pending_manual_override_payload is None


@pytest.mark.parametrize("prior", [
    {"selected":True,"word":"old","human_note":"don't discard"},
    {"selected":True,"word":"foreign","engine":"manual"},
    {"selected":True,"word":"old","source_x":25},
    "not an override record",
])
def test_owned_manual_override_unknown_fields_or_source_word_refuse(tmp_path, prior):
    view, path, deps = scene(tmp_path)
    path.write_text(json.dumps({"version":1,"page":"page",
        "overrides":{"cid":prior,"other":{"selected":False,"word":"keep","engine":"human"}}}),
        encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="人工|来源"):
        view._write_manual_override({"candidate_id":"cid","word":"old"}, selected=False, defer=True)
    assert path.read_bytes() == before
    assert view._pending_manual_override_path is None


@pytest.mark.parametrize("foreign", ["same_id", "other_id", "deleted", "created_after_absent"])
def test_foreign_bytes_between_checkbox_and_deferred_flush_fail_closed(tmp_path, foreign):
    view, path, deps = scene(tmp_path)
    before = {"version":1,"page":"page","overrides":{
        "other":{"selected":True,"word":"another human","engine":"manual"},
    }}
    if foreign != "created_after_absent":
        path.write_text(json.dumps(before), encoding="utf-8")
    previous = path.read_bytes() if path.exists() else None
    view._write_manual_override({"candidate_id":"cid","word":"old"}, selected=True, defer=True)
    assert view._pending_manual_override_origin == (path.resolve(), previous)
    if foreign == "deleted":
        path.unlink()
        new = None
    else:
        changed = dict(before)
        changed["overrides"] = dict(before["overrides"])
        if foreign == "same_id":
            changed["overrides"]["cid"] = {"selected":False,"word":"external"}
        elif foreign == "other_id":
            changed["overrides"]["new_user"] = {"selected":True,"word":"third party"}
        else:
            changed["overrides"]["new_file"] = {"selected":True,"word":"newly created"}
        path.write_text(json.dumps(changed), encoding="utf-8")
        new = path.read_bytes()
    with pytest.raises(RuntimeError):
        view._flush_pending_manual_override()
    assert (path.read_bytes() if path.exists() else None) == new
    assert view._pending_manual_override_path == path
    assert view._pending_manual_override_payload["overrides"]["cid"]["selected"] is True


def test_multiple_checkbox_updates_one_page_keep_all_human_choices_then_atomic_flush(tmp_path):
    view, path, deps = scene(tmp_path)
    original = {"version":1,"page":"page","overrides":{
        "other":{"selected":True,"word":"untouched","engine":"human"},
    }}
    path.write_text(json.dumps(original,ensure_ascii=False),encoding="utf-8")
    old_bytes = path.read_bytes()
    view._write_manual_override({"candidate_id":"a","word":"alpha"}, selected=True, defer=True)
    view._write_manual_override({"candidate_id":"b","word":"beta"}, selected=False, defer=True)
    view._write_manual_override({"candidate_id":"a","word":"alpha"}, selected=False, defer=True)
    assert path.read_bytes() == old_bytes
    view._flush_pending_manual_override()
    result = json.loads(path.read_text("utf-8"))["overrides"]
    assert result["other"] == original["overrides"]["other"]
    assert result["a"] == {"selected":False,"word":"alpha","engine":"manual"}
    assert result["b"] == {"selected":False,"word":"beta","engine":"manual"}
    assert view._pending_manual_override_path is None
    assert "_pending_manual_override_origin" not in view.__dict__


def test_page_switch_flushes_original_page_using_frozen_page_not_current(tmp_path):
    view, path, deps = scene(tmp_path)
    path2 = tmp_path / "second_manual_selection.json"
    view._write_manual_override({"candidate_id":"one","word":"first"},selected=True,defer=True)
    view.current_page = SimpleNamespace(stem="second")
    view._manual_selection_path = lambda: path2
    view._write_manual_override({"candidate_id":"two","word":"second"},selected=True,defer=True)
    assert json.loads(path.read_text("utf-8"))["page"] == "page"
    assert not path2.exists()
    view._flush_pending_manual_override()
    assert json.loads(path2.read_text("utf-8"))["page"] == "second"


def test_failed_atomic_replace_never_truncates_original_manual_file(tmp_path, monkeypatch):
    view, path, deps = scene(tmp_path)
    previous = {"version":1,"page":"page","overrides":{
        "other":{"selected":True,"word":"original human","engine":"manual"},
    }}
    path.write_text(json.dumps(previous),encoding="utf-8")
    original = path.read_bytes()
    view._write_manual_override({"candidate_id":"new","word":"new"},selected=True,defer=True)
    def fail(path, data):
        raise OSError("simulated disk full before replacement")
    monkeypatch.setattr(owner, "_atomic_bytes",fail)
    with pytest.raises(OSError,match="disk full"):
        view._flush_pending_manual_override()
    assert path.read_bytes()==original
    assert view._pending_manual_override_path==path


def test_corrupted_manual_source_blocks_checkbox_before_any_model_change(tmp_path):
    view, path, deps = scene(tmp_path)
    path.write_bytes(b"broken human edits")
    cand={"candidate_id":"cid","word":"head","source_x":10,"source_y":20,
          "selected":False}
    view.ocr_review_candidates=[cand]
    view.entries=[]
    view.candidate_check_vars={}
    view._claim_page_for_manual_edit=lambda: True
    attempts=[]
    view.status_var=SimpleNamespace(set=attempts.append)
    view._queue_proofreading_candidate_evidence=lambda *a: attempts.append("queue")
    view._sync_entry_editor_texts=lambda: attempts.append("sync")
    assert owner.set_candidate_selected(view,SimpleNamespace(WordEntry=object),cand,True) is False
    assert cand["selected"] is False and view.entries==[]
    assert attempts and "损坏" in attempts[-1]
    assert "queue" not in attempts and "sync" not in attempts
    assert path.read_bytes()==b"broken human edits"


def test_position_switch_checks_sibling_human_record_before_any_checkbox_mutation(tmp_path):
    view,path,deps=scene(tmp_path)
    sibling={"candidate_id":"other","word":"prior","position_group_id":"physical",
             "selected":True}
    cand={"candidate_id":"cid","word":"new","position_group_id":"physical",
          "selected":False}
    view.ocr_review_candidates=[sibling,cand]
    view.candidate_check_vars={}
    view.entries=[]
    view._claim_page_for_manual_edit=lambda: True
    attempts=[]
    view.status_var=SimpleNamespace(set=attempts.append)
    view._queue_proofreading_candidate_evidence=lambda *a: attempts.append("queued")
    view._sync_entry_editor_texts=lambda: attempts.append("synced")
    path.write_text(json.dumps({"version":1,"page":"page","overrides":{
        "other":{"selected":True,"word":"prior","engine":"manual",
                 "human_note":"important"}}}),encoding="utf-8")
    original=path.read_bytes()
    assert owner.set_candidate_selected(view,SimpleNamespace(WordEntry=object),cand,True) is False
    assert cand["selected"] is False and sibling["selected"] is True
    assert not attempts or ("queued" not in attempts and "synced" not in attempts)
    assert path.read_bytes()==original and view.entries==[]
