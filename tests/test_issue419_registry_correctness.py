"""Issue #419: lifetime and cross-instance data-loss regressions."""
from concurrent.futures import ThreadPoolExecutor
import gc
from pathlib import Path
import threading
from types import SimpleNamespace
import weakref

from picture_capture import entry_classification as cls, recent_projects
from picture_capture.models import Entry


def test_entry_classification_follows_concrete_slotted_entry_lifetime():
    baseline = len(cls._ENTRY_OWNER)
    obj = Entry("old", 10, 20)
    cls.set_entry_scale_manual(obj, "oversized")
    assert cls.get_entry_classification(obj).manual_override
    owner_id = id(obj)
    owner_ref = weakref.ref(obj)
    del obj
    gc.collect()
    assert owner_ref() is None
    assert owner_id not in cls._ENTRY_OWNER
    assert owner_id not in cls._ENTRY_META
    assert len(cls._ENTRY_OWNER) <= baseline


def test_entry_identity_not_signature_controls_registry():
    entry = Entry("x", 7, 9)
    cls.set_entry_scale_manual(entry, "oversized")
    assert cls.get_entry_classification(entry).manual_override
    # Model a recycled ID collision without depending on CPython allocator.
    other = Entry("another", 7, 9)
    cls._ENTRY_META[id(other)] = cls._ENTRY_META[id(entry)]
    cls._ENTRY_OWNER[id(other)] = cls._ENTRY_OWNER[id(entry)]
    assert cls.get_entry_classification(other).manual_override is False
    assert cls.get_entry_classification(entry).manual_override is True


def test_nonweakrefable_lines_are_bounded_and_identity_checked():
    line = SimpleNamespace(role="body")
    evidence = Entry("large", 1, 2, ocr_source="ordinary_large_head_evidence")
    cls.register_layout_line_classification(line, evidence)
    assert cls.get_layout_line_classification(line).entry_scale == "oversized"
    another = SimpleNamespace(role="body")
    cls._LINE_META[id(another)] = cls._LINE_META[id(line)]
    assert cls.get_layout_line_classification(another).entry_scale == "regular"
    for i in range(cls._LINE_CACHE_LIMIT + 30):
        cls.register_layout_line_classification(SimpleNamespace(role=str(i)), evidence)
    assert len(cls._LINE_META) <= cls._LINE_CACHE_LIMIT


def test_recent_touch_serializes_entire_read_modify_write(tmp_path, monkeypatch):
    target = tmp_path / "recent_projects.json"
    p1 = tmp_path / "project-a"
    p2 = tmp_path / "project-b"
    p1.mkdir()
    p2.mkdir()
    entered = threading.Event()
    unblock = threading.Event()
    original_load = recent_projects.load_recent_projects
    once = [False]

    def paused_first_load(path=None):
        result = original_load(path)
        if not once[0]:
            once[0] = True
            entered.set()
            assert unblock.wait(5), "first transaction stuck"
        return result

    monkeypatch.setattr(recent_projects, "load_recent_projects", paused_first_load)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(recent_projects.touch_recent_project, p1, target)
        assert entered.wait(5)
        second = pool.submit(recent_projects.touch_recent_project, p2, target)
        unblock.set()
        first.result(timeout=10)
        second.result(timeout=10)
    rows = original_load(target)
    assert {row["path"] for row in rows} == {str(p1), str(p2)}


def test_pin_and_remove_use_same_transaction_lock(tmp_path):
    target = tmp_path / "recent_projects.json"
    a = tmp_path / "a"
    a.mkdir()
    recent_projects.touch_recent_project(a, target)
    recent_projects.set_recent_project_pinned(a, True, target)
    assert recent_projects.load_recent_projects(target)[0]["pinned"] is True
    recent_projects.remove_recent_project(a, target)
    assert recent_projects.load_recent_projects(target) == []
