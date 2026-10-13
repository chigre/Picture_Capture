"""Issue #419: cache invalidation and bounded CPU/memory/network resources."""
from __future__ import annotations

import gc
import io
import json
import os
from pathlib import Path
import weakref

from PIL import Image
import pytest

from picture_capture import cc_cedict, layout_core_understanding as core, network_lookup, project_storage


def test_manifest_cache_hit_then_atomic_replacement(tmp_path):
    path = project_storage.manifest_path(tmp_path)
    path.parent.mkdir()
    payload = {"format": project_storage.PROJECT_FORMAT, "format_version": 2}
    path.write_text(json.dumps(payload), encoding="utf-8")
    project_storage.clear_managed_manifest_cache()
    assert project_storage.is_managed_project(tmp_path)
    assert project_storage.is_managed_project(tmp_path)
    assert project_storage._parse_managed_manifest_cached.cache_info().hits >= 1
    replaced = path.with_suffix(".new")
    replaced.write_text(json.dumps({**payload, "format_version": 1}), encoding="utf-8")
    os.utime(replaced, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns))
    os.replace(replaced, path)
    assert not project_storage.is_managed_project(tmp_path)


def test_cedict_external_replacement_with_preserved_mtime_invalidates(tmp_path, monkeypatch):
    path = tmp_path / cc_cedict.DATA_FILENAME
    path.write_text("旧 舊 [jiu4] /old/\n", encoding="utf-8")
    monkeypatch.setattr(cc_cedict, "data_path", lambda: path)
    cc_cedict.clear_cache()
    try:
        first, count, _ = cc_cedict._load_index()
        assert "旧" in first
        assert count == 1
        new = tmp_path / "replacement"
        new.write_text("新 新 [xin1] /new/\n", encoding="utf-8")
        os.utime(new, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns))
        os.replace(new, path)
        next_words, _, _ = cc_cedict._load_index()
        assert "新" in next_words
        assert "旧" not in next_words
    finally:
        cc_cedict.clear_cache()


def test_network_response_is_limited_to_1mib(monkeypatch):
    monkeypatch.setattr(network_lookup, "urlopen", lambda *_args, **_kw: io.BytesIO(b"x" * (network_lookup.MAX_JSON_RESPONSE_BYTES + 2)))
    with pytest.raises(ValueError, match="exceeds"):
        network_lookup._read_json("https://example.invalid", 2)
    monkeypatch.setattr(network_lookup, "urlopen", lambda *_args, **_kw: io.BytesIO(b'{"ok":true}'))
    assert network_lookup._read_json("https://example.invalid", 2) == {"ok": True}


def test_network_executor_is_shared_and_bounded(monkeypatch):
    monkeypatch.setattr(network_lookup, "_lookup_wiktionary", lambda word, timeout: network_lookup.LookupSourceResult("wiki", True, "example"))
    worker_pool = network_lookup._LOOKUP_EXECUTOR
    for _ in range(8):
        output = network_lookup.lookup_word_free("abc")
        assert output.found
        assert network_lookup._LOOKUP_EXECUTOR is worker_pool
    assert len(worker_pool._threads) <= 3


def test_large_layout_digest_streams_identical_bytes(tmp_path, monkeypatch):
    image = Image.new("RGB", (160, 130), "white")
    image.putpixel((90, 120), (17, 22, 130))
    monkeypatch.setattr(core, "_FINGERPRINT_STREAM_THRESHOLD", 1)
    monkeypatch.setattr(core, "_FINGERPRINT_CHUNK_BYTES", 4096)
    chunked = core._image_fingerprint(image)
    monkeypatch.setattr(core, "_FINGERPRINT_STREAM_THRESHOLD", 10**12)
    whole = core._image_fingerprint(image)
    assert chunked == whole


def test_mutable_image_does_not_reuse_cached_layout_fingerprint():
    core.clear_layout_understanding_cache()
    image = Image.new("RGB", (16, 16), "white")
    image.readonly = 1
    before = core._image_fingerprint(image)
    assert core._image_fingerprint(image) == before
    image.putpixel((0, 0), (0, 0, 0))
    assert not image.readonly
    after = core._image_fingerprint(image)
    assert after != before
    key = id(image)
    assert key not in core._READONLY_IMAGE_DIGESTS


def test_readonly_image_gc_releases_fingerprint_state():
    image = Image.new("RGB", (8, 8), "white")
    image.readonly = 1
    core._image_fingerprint(image)
    key = id(image)
    owner = weakref.ref(image)
    del image
    gc.collect()
    assert owner() is None
    assert key not in core._READONLY_IMAGE_DIGESTS
