"""Issue #562: manual classification sidecars have one read/modify/publish transaction.

Synthetic thread interleavings prove same-process ordering only. The public
EntryClassification model and persisted JSON-v1 format are unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path
from threading import Event, Thread, current_thread

import pytest

from picture_capture import entry_classification as cls
from picture_capture.models import Entry


def _pair() -> list[Entry]:
    return [
        Entry(word="甲", x=12, y=34, ocr_source="ordinary_large_head_evidence"),
        Entry(word="乙", x=50, y=85, ocr_source="ordinary_large_head_evidence"),
    ]


def test_concurrent_sidecar_writers_preserve_both_manual_corrections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdic = tmp_path / "page.pdic"
    first_entries = _pair()
    second_entries = _pair()
    cls.set_entry_scale_manual(first_entries[0], "regular")
    cls.set_entry_scale_manual(second_entries[1], "regular")

    first_read = Event()
    release_first = Event()
    second_started = Event()
    errors: list[BaseException] = []
    results: list[bool] = []
    original_read = cls._read_sidecar

    def pause_after_first_read(path: Path):
        rows = original_read(path)
        if current_thread().name == "classification-first":
            first_read.set()
            if not release_first.wait(8):
                raise TimeoutError("first transaction was not released")
        return rows

    monkeypatch.setattr(cls, "_read_sidecar", pause_after_first_read)

    def save(entries: list[Entry], started: Event | None = None) -> None:
        if started is not None:
            started.set()
        try:
            results.append(cls.write_classification_sidecar(entries, pdic))
        except BaseException as exc:
            errors.append(exc)

    first = Thread(target=save, args=(first_entries,), name="classification-first", daemon=True)
    second = Thread(
        target=save, args=(second_entries, second_started),
        name="classification-second", daemon=True,
    )
    try:
        first.start()
        assert first_read.wait(5), "first writer did not reach the sidecar read"
        second.start()
        assert second_started.wait(5), "second writer never began"
        second.join(timeout=0.25)
        assert second.is_alive(), "second writer bypassed first read/modify/publish"
    finally:
        release_first.set()
        first.join(timeout=8)
        if second.ident is not None:
            second.join(timeout=8)

    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert results == [True, True]
    rows = json.loads(cls.classification_sidecar_path(pdic).read_text(encoding="utf-8"))
    assert rows["format"] == cls.SIDECAR_FORMAT
    assert [(row["word"], row["manual_override"], row["entry_scale"]) for row in rows["entries"]] == [
        ("甲", True, "regular"),
        ("乙", True, "regular"),
    ]
    restored = _pair()
    cls.apply_classification_sidecar(restored, pdic)
    assert all(cls.get_entry_classification(entry).manual_override for entry in restored)
    assert all(cls.get_entry_classification(entry).entry_scale == "regular" for entry in restored)


def test_sidecar_reader_waits_for_manual_override_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdic = tmp_path / "page.pdic"
    manual = _pair()
    cls.set_entry_scale_manual(manual[0], "regular")
    restored = _pair()
    read_started = Event()
    writer_read = Event()
    release_writer = Event()
    errors: list[BaseException] = []
    observed: list[tuple[str, bool]] = []
    original_read = cls._read_sidecar

    def pause_writer(path: Path):
        rows = original_read(path)
        if current_thread().name == "classification-writer":
            writer_read.set()
            if not release_writer.wait(8):
                raise TimeoutError("writer was not released")
        return rows

    monkeypatch.setattr(cls, "_read_sidecar", pause_writer)

    def writer() -> None:
        try:
            cls.write_classification_sidecar(manual, pdic)
        except BaseException as exc:
            errors.append(exc)

    def reader() -> None:
        read_started.set()
        try:
            cls.apply_classification_sidecar(restored, pdic)
            meta = cls.get_entry_classification(restored[0])
            observed.append((meta.entry_scale, meta.manual_override))
        except BaseException as exc:
            errors.append(exc)

    first = Thread(target=writer, name="classification-writer", daemon=True)
    second = Thread(target=reader, name="classification-reader", daemon=True)
    try:
        first.start()
        assert writer_read.wait(5)
        second.start()
        assert read_started.wait(5)
        second.join(timeout=0.25)
        assert second.is_alive(), "reader observed an unpublished sidecar"
    finally:
        release_writer.set()
        first.join(timeout=8)
        if second.ident is not None:
            second.join(timeout=8)

    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert observed == [("regular", True)]


def test_sidecar_replace_failure_preserves_previous_manual_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdic = tmp_path / "page.pdic"
    entries = _pair()
    cls.set_entry_scale_manual(entries[0], "regular")
    assert cls.write_classification_sidecar(entries, pdic)
    sidecar = cls.classification_sidecar_path(pdic)
    before = sidecar.read_bytes()
    original_replace = cls.os.replace

    def refuse_replace(source, target) -> None:
        if Path(target) == sidecar:
            raise OSError("synthetic sidecar replace failure")
        original_replace(source, target)

    monkeypatch.setattr(cls.os, "replace", refuse_replace)
    cls.set_entry_scale_manual(entries[1], "regular")
    with pytest.raises(OSError, match="synthetic sidecar replace failure"):
        cls.write_classification_sidecar(entries, pdic)
    assert sidecar.read_bytes() == before
    assert not list(sidecar.parent.glob(f".{sidecar.name}.*.tmp"))
