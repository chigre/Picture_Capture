"""Issue #562: same-process manifest readers and refreshes share one transaction lock.

A Windows replace can fail while another thread holds the destination file
open. These synthetic interleavings do not claim cross-process guarantees.
"""
from __future__ import annotations

from pathlib import Path
from threading import Event, Thread, current_thread
import json

import pytest

from picture_capture.persistence import project_storage as storage


def test_managed_manifest_reader_cannot_overlap_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "project"
    storage.ensure_project_storage(root, "1.0")
    manifest = storage.manifest_path(root)
    storage.clear_managed_manifest_cache()

    reader_entered = Event()
    reader_inside = Event()
    release_reader = Event()
    writer_started = Event()
    errors: list[BaseException] = []
    reader_results: list[bool] = []
    original_parse = storage._parse_managed_manifest_cached
    original_replace = storage.os.replace

    def paused_parse(path_string: str, identity: tuple[int, ...]) -> bool:
        if current_thread().name != "manifest-reader":
            return original_parse(path_string, identity)
        reader_inside.set()
        reader_entered.set()
        try:
            if not release_reader.wait(8):
                raise TimeoutError("test reader release timed out")
            return original_parse(path_string, identity)
        finally:
            reader_inside.clear()

    def emulate_windows_replace(source, destination):
        if Path(destination) == manifest and reader_inside.is_set():
            raise PermissionError("emulated Windows open-reader replacement refusal")
        return original_replace(source, destination)

    # Preserve the decorated parser's public cache interface. The writer
    # invalidates it after publication, including during this interleaving.
    paused_parse.cache_clear = original_parse.cache_clear
    paused_parse.cache_info = original_parse.cache_info
    monkeypatch.setattr(storage, "_parse_managed_manifest_cached", paused_parse)
    monkeypatch.setattr(storage.os, "replace", emulate_windows_replace)

    def read() -> None:
        try:
            reader_results.append(storage.is_managed_project(root))
        except BaseException as exc:
            errors.append(exc)

    def write() -> None:
        writer_started.set()
        try:
            storage.ensure_project_storage(root, "2.0")
        except BaseException as exc:
            errors.append(exc)

    reader = Thread(target=read, name="manifest-reader", daemon=True)
    writer = Thread(target=write, name="manifest-writer", daemon=True)
    try:
        reader.start()
        assert reader_entered.wait(5), "reader never reached the manifest parser"
        writer.start()
        assert writer_started.wait(5)
        # An unguarded writer can reach os.replace while the reader is paused.
        # The correct implementation waits until this read transaction ends.
        writer.join(timeout=0.25)
        assert writer.is_alive(), "writer bypassed active manifest reader"
    finally:
        release_reader.set()
        reader.join(timeout=8)
        if writer.ident is not None:
            writer.join(timeout=8)

    assert not reader.is_alive() and not writer.is_alive()
    assert errors == []
    assert reader_results == [True]
    assert json.loads(manifest.read_text(encoding="utf-8"))["last_opened_with"] == "2.0"


def test_manifest_read_modify_publish_preserves_order_and_existing_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "project"
    storage.ensure_project_storage(root, "1.0")
    manifest = storage.manifest_path(root)
    saved = json.loads(manifest.read_text(encoding="utf-8"))
    saved["external_metadata"] = "保留原值"
    manifest.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")

    first_at_publish = Event()
    release_first = Event()
    first_published = Event()
    second_started = Event()
    early_second_reads: list[str] = []
    errors: list[BaseException] = []
    real_publish = storage._write_json_atomic
    real_read = Path.read_text

    def observed_read(self: Path, *args, **kwargs) -> str:
        if (
            self == manifest
            and current_thread().name == "manifest-second"
            and first_at_publish.is_set()
            and not first_published.is_set()
        ):
            early_second_reads.append("read before first commit")
        return real_read(self, *args, **kwargs)

    def paused_publish(path: Path, payload: dict) -> None:
        is_first = current_thread().name == "manifest-first"
        if is_first:
            first_at_publish.set()
            if not release_first.wait(8):
                raise TimeoutError("first writer release timed out")
        try:
            real_publish(path, payload)
        finally:
            if is_first:
                first_published.set()

    monkeypatch.setattr(Path, "read_text", observed_read)
    monkeypatch.setattr(storage, "_write_json_atomic", paused_publish)

    def refresh(version: str, started: Event | None = None) -> None:
        if started is not None:
            started.set()
        try:
            storage.ensure_project_storage(root, version)
        except BaseException as exc:
            errors.append(exc)

    first = Thread(target=refresh, args=("2.20",), name="manifest-first", daemon=True)
    second = Thread(target=refresh, args=("2.21", second_started), name="manifest-second", daemon=True)
    try:
        first.start()
        assert first_at_publish.wait(5), "first writer did not reach publish"
        second.start()
        assert second_started.wait(5)
        second.join(timeout=0.25)
        assert second.is_alive(), "second refresh bypassed first transaction"
    finally:
        release_first.set()
        first.join(timeout=8)
        if second.ident is not None:
            second.join(timeout=8)

    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert early_second_reads == []
    result = json.loads(manifest.read_text(encoding="utf-8"))
    assert result["created_with"] == "1.0"
    assert result["last_opened_with"] == "2.21"
    assert result["external_metadata"] == "保留原值"
    assert storage.is_managed_project(root)
