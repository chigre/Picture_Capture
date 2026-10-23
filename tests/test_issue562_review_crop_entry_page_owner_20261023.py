"""ReviewWindow crop/editor/page owner contracts and critical transaction parity."""
from __future__ import annotations

import ast
import inspect
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture import app as shell
from picture_capture.ui import (
    review_crop_actions as crop,
    review_entry_actions as entry,
    review_page_lifecycle as page,
)

SOURCE = Path(__file__).resolve().parents[1] / "src/picture_capture"
GROUPS = {
    "review_crop_actions.py": [
        "_update_active_crop_preview",
        "_schedule_review_crop_height_update",
        "_refresh_review_row_crop",
        "_ordinary_review_photo"
    ],
    "review_entry_actions.py": [
        "set_active",
        "_scroll_editor_into_view",
        "focus_index",
        "on_key",
        "_set_editor_membership_color",
        "delete_review_entry",
        "_save_digit_map",
        "insert_char",
        "_selected_wordslist_global_index",
        "use_selected_word",
        "fill_words"
    ],
    "review_page_lifecycle.py": [
        "_finish_close_review",
        "autosave_commit",
        "_review_evidence_before_save",
        "_review_evidence_after_save",
        "save",
        "_reset_rows_scroll_top",
        "_prefetch_path_signature",
        "_page_prefetch_signature_for",
        "_page_prefetch_signature",
        "_review_prefetch_key",
        "_take_prefetched_page",
        "_schedule_adjacent_preload",
        "change_page"
    ]
}
SYMBOLS = {
    "review_crop_actions.py": ("_review_crop", "_review_crop_deps"),
    "review_entry_actions.py": ("_review_entry", "_review_entry_deps"),
    "review_page_lifecycle.py": ("_review_page", "_review_page_deps"),
}


@pytest.mark.parametrize("filename", list(GROUPS))
def test_exact_physical_owner_and_unchanged_tk_delegate(filename):
    owner_tree = ast.parse((SOURCE / "ui" / filename).read_text(encoding="utf-8"))
    root = ast.parse((SOURCE / "app.py").read_text(encoding="utf-8"))
    clazz = next(n for n in root.body if isinstance(n, ast.ClassDef) and n.name == "ReviewWindow")
    owner = {n.name: n for n in owner_tree.body if isinstance(n, ast.FunctionDef)}
    shell_methods = {n.name: n for n in clazz.body if isinstance(n, ast.FunctionDef)}
    symbol, factory = SYMBOLS[filename]
    for name in GROUPS[filename]:
        assert name in owner and name in shell_methods, name
        calls = [n for n in ast.walk(shell_methods[name]) if isinstance(n, ast.Call)]
        assert any(isinstance(n.func, ast.Attribute) and n.func.attr == name
                   and isinstance(n.func.value, ast.Name) and n.func.value.id == symbol
                   for n in calls), name
        assert any(isinstance(n.func, ast.Name) and n.func.id == factory for n in calls), name
    assert not any(isinstance(n, ast.ImportFrom) and n.module == "app"
                   for n in ast.walk(owner_tree))


def test_static_class_method_and_keyword_only_page_save_abi():
    cls = shell.ReviewWindow
    assert isinstance(inspect.getattr_static(cls, "_prefetch_path_signature"), staticmethod)
    assert isinstance(inspect.getattr_static(cls, "_page_prefetch_signature_for"), classmethod)
    assert list(inspect.signature(cls._prefetch_path_signature).parameters) == ["path"]
    assert list(inspect.signature(cls._page_prefetch_signature_for).parameters) == [
        "project_root", "page",
    ]
    signature = inspect.signature(cls.save)
    assert signature.parameters["redraw_main"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["redraw_main"].default is True


def test_original_live_helpers_stay_patchable(monkeypatch):
    token = object()
    monkeypatch.setattr(shell, "_review_crop_context", token)
    monkeypatch.setattr(shell, "sync_review_entry_classification", token)
    monkeypatch.setattr(shell, "read_pdic", token)
    assert shell._review_crop_deps()._review_crop_context is token
    assert shell._review_entry_deps().sync_review_entry_classification is token
    assert shell._review_page_deps().read_pdic is token


def test_crop_height_debounce_replaces_previous_job():
    canceled, scheduled = [], []
    view = SimpleNamespace(
        vars=[SimpleNamespace(get=lambda: "字")],
        _review_crop_single_flags=[False],
        _review_crop_height_jobs={0: "older"},
        after_cancel=canceled.append,
        after=lambda milliseconds, callback: scheduled.append((milliseconds, callback)) or "new",
        _refresh_review_row_crop=lambda idx: None,
    )
    crop._schedule_review_crop_height_update(
        view, SimpleNamespace(tk=SimpleNamespace(TclError=Exception),
                              _focused_review_is_single_character=lambda text: True), 0,
    )
    assert canceled == ["older"] and scheduled[0][0] == 120
    assert view._review_crop_height_jobs[0] == "new"


def test_stale_prefetch_is_consumed_but_rejected():
    path = Path("page.png")
    view = SimpleNamespace(
        parent=SimpleNamespace(project=SimpleNamespace(root=Path("root"), images=[path])),
        _prefetch_lock=threading.Lock(),
        _prefetched_pages={0: {"project_root": "root", "signature": ("old",)}},
        _page_prefetch_signature=lambda page: ("new",),
    )
    assert page._take_prefetched_page(view, SimpleNamespace(), 0) is None
    assert view._prefetched_pages == {}
    view._prefetched_pages[0] = {"project_root": "root", "signature": ("new",), "review_crops": []}
    assert page._take_prefetched_page(view, SimpleNamespace(), 0)["review_crops"] == []


def test_original_prefetch_file_signature_uses_size_and_mtime(tmp_path):
    path = tmp_path / "source.png"
    deps = SimpleNamespace()
    assert page._prefetch_path_signature(deps, path) == (False, 0, 0)
    path.write_bytes(b"abc")
    found, size, modified = page._prefetch_path_signature(deps, path)
    assert found and size == 3 and modified > 0


def test_page_change_saves_old_page_before_consuming_prefetch():
    calls = []
    parent = SimpleNamespace(
        current_index=8,
        change_page=lambda delta, **kwargs: calls.append(("change", delta, kwargs)),
    )
    view = SimpleNamespace(
        parent=parent, _filter_rows_active=False,
        save=lambda **kwargs: calls.append(("save", kwargs)) or True,
        _take_prefetched_page=lambda target: calls.append(("prefetch", target)) or {"index": target},
    )
    page.change_page(view, SimpleNamespace(), 1)
    assert [c[0] for c in calls] == ["save", "prefetch", "change"]
    assert calls[0][1] == {"redraw_main": False}
    assert calls[1][1] == 9
    assert calls[2][2] == {
        "preloaded": {"index": 9},
        "current_already_saved": True,
        "async_allowed": False,
    }


def test_filter_page_change_isolated_from_normal_save():
    calls = []
    view = SimpleNamespace(
        _filter_rows_active=True,
        change_filter_batch=lambda n: calls.append(("filter", n)),
    )
    page.change_page(view, SimpleNamespace(), -1)
    assert calls == [("filter", -1)]


def test_entry_wordlist_selection_uses_window_global_index():
    view = SimpleNamespace(word_selected_local_index=2, word_window_indices=[100, 101, 102])
    assert entry._selected_wordslist_global_index(view, SimpleNamespace()) == 102
    view.word_selected_local_index = 99
    assert entry._selected_wordslist_global_index(view, SimpleNamespace()) is None


def test_no_rebuild_or_tk_image_in_background_pure_crop_worker():
    source = (SOURCE / "ui/review_crop_actions.py").read_text(encoding="utf-8")
    worker = source.split("    def worker():", 1)[1].split("    def done(", 1)[0]
    assert "ImageTk" not in worker and "self.after(" not in worker
    assert "_review_crop_context(" in worker and "_review_line_box(" in worker


def test_saved_before_page_switch_and_delete_evidence_markers_maintained():
    source = (SOURCE / "ui/review_page_lifecycle.py").read_text(encoding="utf-8")
    deleted = (SOURCE / "ui/review_entry_actions.py").read_text(encoding="utf-8")
    for marker in ("current_already_saved=True", "async_allowed=False", "_prefetch_closed",
                   "capture_review_before", "record_review_after", "protect_review_pdic_commit"):
        assert marker in source
    for marker in ("candidate_id_unique", "capture_saved_review_deletion",
                   "simplified_entry_key(entry.x, entry.y)", "record_review_after"):
        assert marker in deleted
