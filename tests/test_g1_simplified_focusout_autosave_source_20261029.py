"""G1 fail-first: unreported Tk simplified text must not vanish on autosave.

A StringVar update (e.g. platform text-service edit) does not guarantee
<KeyRelease> / <<Paste>>. Reproduce the unchanged dirty-set save gate rather
than assuming that an event was delivered.
"""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui import review_page_lifecycle
from picture_capture.ui import review_transaction_actions
from picture_capture.proofreading import review_bundle, save_safety


class Var:
    def __init__(self, value: str):
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


def make_review(tmp_path: Path, *, manual: bool = False):
    events: list[str] = []
    entry = SimpleNamespace(word="繁體", x=14, y=128)
    original = Var("繁體")
    simplified = Var("简体")
    parent = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path),
        current_page=tmp_path / "001.png",
        current_index=0,
        entries=[entry],
        settings=SimpleNamespace(review_zoom_percent=100, to_json=lambda _path: None),
        _foreground_batch_state=lambda _index: "idle",
        _claim_page_for_manual_edit=lambda: events.append("claim") or True,
    )
    review = SimpleNamespace(
        parent=parent,
        row_entries=[entry],
        vars=[original],
        simplified_vars=[simplified],
        simplified_actual_values=["简体"],
        simplified_manual_flags=[manual],
        _rendered_page_stem="001",
        _filter_rows_active=False,
        _simplified_dirty_pages=set(),
        _bound_row_entries=lambda: [entry],
        _simplified_display_from_value=lambda word, value, is_manual:
            ("√" if not is_manual and value == word else value),
        _review_evidence_before_save=lambda: None,
        _review_evidence_after_save=lambda _prior: None,
        _commit_edits=lambda: events.append("commit"),
        _stored_review_zoom_percent=lambda: 100,
    )
    return review, simplified, events


def fake_commits(monkeypatch, events):
    monkeypatch.setattr(
        review_transaction_actions, "capture_review_before", lambda _r: object(),
    )
    monkeypatch.setattr(
        review_transaction_actions, "record_review_after", lambda *_a: None,
    )
    monkeypatch.setattr(
        save_safety, "protect_review_pdic_commit", lambda _r: nullcontext(),
    )
    monkeypatch.setattr(
        review_bundle, "commit_review_bundle",
        lambda _r, _before: events.append("bundle"),
    )


def test_autosave_detects_unreported_simplified_editor_change(tmp_path, monkeypatch):
    review, visible, events = make_review(tmp_path)
    fake_commits(monkeypatch, events)
    # Unchanged visible text must not cause a needless write.
    assert review_page_lifecycle.autosave_commit(review, None) is True
    assert events == []
    # Modify the live Tk text WITHOUT a key/clipboard callback.
    visible.set("人工改词")
    assert review._simplified_dirty_pages == set()
    assert review_page_lifecycle.autosave_commit(review, None) is True
    assert events == ["commit", "bundle"]


def test_autosave_does_not_rewrite_untouched_manual_simplified(tmp_path, monkeypatch):
    review, _visible, events = make_review(tmp_path, manual=True)
    fake_commits(monkeypatch, events)
    assert review_page_lifecycle.autosave_commit(review, None) is True
    assert events == []


def test_pending_page_save_claims_unreported_simplified_change(tmp_path, monkeypatch):
    review, visible, events = make_review(tmp_path)
    fake_commits(monkeypatch, events)
    review.parent._foreground_batch_state = lambda _index: "pending"
    visible.set("人工改词")
    deps = SimpleNamespace(settings_path=lambda root: root / "settings.json")
    assert review_page_lifecycle.save(review, deps, redraw_main=False) is True
    assert events == ["claim", "commit", "bundle"]


def test_unchanged_manual_focusout_remains_readonly(tmp_path):
    from picture_capture.ui import review_simplified_workflow

    review, _visible, events = make_review(tmp_path, manual=True)
    review._simplified_page_records = lambda _stem: {}
    review.active_index = -1
    deps = SimpleNamespace(simplified_entry_key=lambda x, y: f"{x}:{y}")
    review_simplified_workflow.on_simplified_key(
        review, deps, SimpleNamespace(), 0,
    )
    assert events == []
    assert review._simplified_dirty_pages == set()


def test_simplified_editor_has_focusout_fallback_binding():
    source = (
        Path(__file__).resolve().parents[1]
        / "src/picture_capture/ui/review_workspace_workflow.py"
    ).read_text(encoding="utf-8")
    assert 'simplified_editor.bind("<FocusOut>"' in source
