"""G1: checkbox source pins and PDIC/manual delayed-publication fault matrix.

Synthetic page/sidecar files only; these tests do not constitute Windows E3.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from picture_capture.io.formats import pdic_path
from picture_capture.models import Entry
from picture_capture.proofreading.deferred_save import flush_deferred_page_save
from picture_capture.ui import main_pdic_persistence as regular
from picture_capture.ui import review_selection_workflow as selection


def _case(tmp_path):
    page = tmp_path / "page.png"
    page.write_bytes(b"synthetic page pixels, not a real scan")
    pdic = pdic_path(page)
    pdic.write_bytes(b"previous PDIC user bytes")
    manual = tmp_path / "page_manual_selection.json"
    events = []
    app = SimpleNamespace(
        current_page=page, project=SimpleNamespace(root=tmp_path, images=[page]),
        image=SimpleNamespace(width=100), entries=[Entry("new", 10, 20)],
        entry_editor_bindings=[], current_index=0,
        _deferred_save_job=None, _deferred_save_page=page,
        _deferred_save_snapshot=(page, [Entry("new", 10, 20)], 100,
                                 ("page", "@", "@"), 0),
        _deferred_save_pdic_origin=(page, pdic.read_bytes()),
        _pending_manual_override_path=None, _pending_manual_override_payload=None,
        _refresh_word_fill_check_from_line_count=lambda *a, **k: events.append("refresh"),
        _update_page_row=lambda *a: events.append("row"),
        _flush_proofreading_candidate_evidence=lambda: events.append("candidate log"),
        _flush_proofreading_add_evidence=lambda: events.append("add log"),
    )
    deps = SimpleNamespace(json=json)
    app._manual_selection_path = lambda: manual
    app._read_manual_overrides = lambda: selection._read_manual_overrides(app, deps)
    app._flush_pending_manual_override = lambda: selection._flush_pending_manual_override(app, deps)
    selection._write_manual_override(
        app, deps, {"candidate_id": "candidate", "word": "new"},
        selected=True, defer=True,
    )
    return app, page, pdic, manual, events


def _flush(app, pdic, write):
    return flush_deferred_page_save(
        app, write_pdic=write, pdic_path=lambda _page: pdic,
    )


def test_external_manual_bytes_refuse_before_deferred_pdic_write(tmp_path):
    app, page, pdic, manual, events = _case(tmp_path)
    manual.write_bytes(b'{"version":1,"page":"page","overrides":{"human":{"selected":true}}}')
    foreign = manual.read_bytes()
    original = pdic.read_bytes()
    def forbidden(*_a):
        pytest.fail("PDIC writer must not run after a foreign human edit")
    with pytest.raises(RuntimeError, match="来源"):
        _flush(app, pdic, forbidden)
    assert manual.read_bytes() == foreign and pdic.read_bytes() == original
    assert app._deferred_save_snapshot[0] == page
    assert app._pending_manual_override_path == manual
    assert not events


def test_external_pdic_bytes_refuse_before_checkbox_overwrites_human(tmp_path):
    app, page, pdic, manual, events = _case(tmp_path)
    pdic.write_bytes(b"foreign proofreader's PDIC")
    with pytest.raises(RuntimeError, match="PDIC 来源"):
        _flush(app, pdic, lambda *_a: pytest.fail("stale PDIC writer"))
    assert pdic.read_bytes() == b"foreign proofreader's PDIC"
    assert not manual.exists()
    assert app._deferred_save_snapshot[0] == page
    assert not events


def test_write_then_raise_is_uncertain_and_never_replays_snapshot(tmp_path):
    app, page, pdic, manual, events = _case(tmp_path)
    def replace_then_fail(*_a):
        pdic.write_bytes(b"already replaced new PDIC")
        raise OSError("injected post-replace exception")
    with pytest.raises(OSError, match="post-replace"):
        _flush(app, pdic, replace_then_fail)
    assert app._deferred_save_uncertain is True
    assert app._deferred_save_snapshot[0] == page
    assert pdic.read_bytes() == b"already replaced new PDIC"
    assert not manual.exists() and not events
    with pytest.raises(RuntimeError, match="uncertain"):
        _flush(app, pdic, lambda *_a: pytest.fail("must not replay"))
    assert pdic.read_bytes() == b"already replaced new PDIC"


def test_pre_replace_failure_keeps_retryable_snapshot(tmp_path):
    app, page, pdic, manual, events = _case(tmp_path)
    original = pdic.read_bytes()
    with pytest.raises(OSError, match="disk full"):
        _flush(app, pdic, lambda *_a: (_ for _ in ()).throw(OSError("disk full")))
    assert pdic.read_bytes() == original
    assert not app.__dict__.get("_deferred_save_uncertain", False)
    assert app._deferred_save_snapshot[0] == page
    _flush(app, pdic, lambda *_a: pdic.write_bytes(b"new PDIC"))
    assert pdic.read_bytes() == b"new PDIC"
    assert json.loads(manual.read_text("utf-8"))["overrides"]["candidate"]["selected"] is True
    assert app._deferred_save_snapshot is None
    assert "_deferred_save_pdic_origin" not in app.__dict__
    assert events == ["refresh", "row", "candidate log", "add log"]


def test_manual_source_race_after_pdic_commit_is_quarantined(tmp_path):
    app, page, pdic, manual, events = _case(tmp_path)
    def conflicting_writer(*_a):
        pdic.write_bytes(b"PDIC committed")
        manual.write_bytes(b'{"version":1,"page":"page","overrides":{"third_party":{"selected":false}}}')
    with pytest.raises(RuntimeError, match="来源"):
        _flush(app, pdic, conflicting_writer)
    assert app._deferred_save_uncertain is True
    assert pdic.read_bytes() == b"PDIC committed"
    assert b"third_party" in manual.read_bytes()
    assert app._deferred_save_snapshot[0] == page
    assert not events


def test_coalesced_checkbox_retains_initial_pdic_source_pin(tmp_path):
    app, page, pdic, manual, events = _case(tmp_path)
    old = app._deferred_save_pdic_origin
    app._deferred_save_snapshot = None  # exercise scheduling from first click
    app.__dict__.pop("_deferred_save_pdic_origin")
    app._deferred_save_delay_ms = 10
    app.pages_tuple = lambda: ("page", "@", "@")
    app.after = lambda _delay, _fn: "job"
    app._flush_deferred_page_save = lambda: None
    from dataclasses import replace
    schedule_deps = SimpleNamespace(
        replace=replace, pdic_path=lambda _p: pdic,
        tk=SimpleNamespace(TclError=RuntimeError),
    )
    selection._schedule_deferred_page_save(app, schedule_deps, sync_editors=False)
    first = app._deferred_save_pdic_origin
    app.after_cancel = lambda _job: None
    selection._schedule_deferred_page_save(app, schedule_deps, sync_editors=False)
    assert first == old == app._deferred_save_pdic_origin


def _regular_app(tmp_path):
    app, page, pdic, manual, events = _case(tmp_path)
    app._batch_active = False
    app._sort_entries_reading_order = lambda: None
    app._sync_entry_editor_texts = lambda: None
    app.pages_tuple = lambda: ("page", "@", "@")
    app._last_pdic_write_changed = False
    return app, page, pdic, manual, events


def test_regular_save_refuses_external_manual_before_pdic(tmp_path):
    app, page, pdic, manual, events = _regular_app(tmp_path)
    manual.write_bytes(b'{"version":1,"page":"page","overrides":{"foreign":{}}}')
    old = pdic.read_bytes()
    with pytest.raises(RuntimeError, match="来源"):
        regular.save_pdic(
            app, deps={"tk": SimpleNamespace(TclError=RuntimeError),
                       "pdic_path": pdic_path,
                       "write_pdic": lambda *_a: pytest.fail("must not overwrite PDIC")},
        )
    assert pdic.read_bytes() == old
    assert app._deferred_save_snapshot[0] == page


def test_regular_save_quarantines_post_pdic_manual_conflict(tmp_path):
    app, page, pdic, manual, events = _regular_app(tmp_path)
    def conflict(*_a):
        pdic.write_bytes(b"regular new PDIC")
        manual.write_bytes(b'{"version":1,"page":"page","overrides":{"foreign":{}}}')
        return True
    with pytest.raises(RuntimeError, match="来源"):
        regular.save_pdic(
            app, deps={"tk": SimpleNamespace(TclError=RuntimeError),
                       "pdic_path": pdic_path, "write_pdic": conflict},
        )
    assert app._deferred_save_uncertain is True
    assert pdic.read_bytes() == b"regular new PDIC"
    assert b"foreign" in manual.read_bytes()
    assert not events
