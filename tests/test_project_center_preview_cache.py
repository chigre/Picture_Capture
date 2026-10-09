"""Persistent Project Center preview cache tests."""
import json
import os
from PIL import Image
from picture_capture import project_center_preview_cache as preview

def test_cache_hit_avoids_original_decode(monkeypatch, tmp_path):
    source = tmp_path / "_cover.png"
    Image.new("RGB", (160, 240), "red").save(source)
    first = preview.load_project_center_preview(tmp_path, source)
    assert first.size == (76, 96)
    cached, metadata = preview._cache_files(tmp_path)
    assert cached.is_file() and metadata.is_file()
    assert json.loads(metadata.read_text(encoding="utf-8"))["name"] == source.name
    def unexpected_decode(_):
        raise AssertionError("cache hit decoded original image")
    monkeypatch.setattr(preview, "_build_card", unexpected_decode)
    again = preview.load_project_center_preview(tmp_path, source)
    assert again.tobytes() == first.tobytes()

def test_changed_source_rebuilds_preview(tmp_path):
    source = tmp_path / "_cover.png"
    Image.new("RGB", (160, 240), "red").save(source)
    first = preview.load_project_center_preview(tmp_path, source)
    Image.new("RGB", (160, 240), "blue").save(source)
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000000))
    changed = preview.load_project_center_preview(tmp_path, source)
    assert changed.tobytes() != first.tobytes()

def test_invalid_cache_is_rebuilt(tmp_path):
    source = tmp_path / "_cover.png"
    Image.new("RGB", (160, 240), "blue").save(source)
    expected = preview.load_project_center_preview(tmp_path, source)
    cached, metadata = preview._cache_files(tmp_path)
    metadata.write_text("broken json", encoding="utf-8")
    assert preview.load_project_center_preview(tmp_path, source).tobytes() == expected.tobytes()
    cached.write_bytes(b"invalid png")
    assert preview.load_project_center_preview(tmp_path, source).tobytes() == expected.tobytes()
    assert cached.parent != tmp_path
