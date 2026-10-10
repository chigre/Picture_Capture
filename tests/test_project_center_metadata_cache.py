"""Persisted project cards must avoid repeated scan inventories."""
from __future__ import annotations

import json
from pathlib import Path

from picture_capture.models import AppSettings
from picture_capture import project_center_metadata_cache as cache
from picture_capture.recent_projects import (
    load_recent_projects, recent_project_details, recent_project_stub_details,
)


def test_metadata_cache_first_paint_and_skip_rescan(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(cache, "user_config_root", lambda: home)
    project = tmp_path / "dictionary"
    project.mkdir()
    (project / "0001.png").write_bytes(b"sample")
    (project / "0002.png").write_bytes(b"sample")
    settings = project / "picture_capture_settings.json"
    settings.write_text(json.dumps({"dictionary_full_name": "Sample Dictionary", "image_suffix": ".png"}))
    registry = tmp_path / "recent.json"
    registry.write_text(json.dumps([{"name": "dictionary", "path": str(project),
                                     "last_page_index": 1}]))
    row = load_recent_projects(registry)[0]
    assert recent_project_stub_details(row)["image_count"] == 0
    scanned = recent_project_details(row)
    assert scanned["image_count"] == 2
    cache.store_details([scanned])
    row = load_recent_projects(registry)[0]
    first_paint = recent_project_stub_details(row)
    assert first_paint["full_name"] == "Sample Dictionary"
    assert first_paint["image_count"] == 2
    assert first_paint["position_text"] == "第 2 / 2 页"
    monkeypatch.setattr(Path, "iterdir", lambda self: (_ for _ in ()).throw(
        AssertionError("unexpected expensive scan")
    ))
    assert recent_project_details(row)["image_count"] == 2


def test_metadata_cache_invalidation_on_added_image(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "user_config_root", lambda: tmp_path / "home")
    project = tmp_path / "dictionary"
    project.mkdir()
    first = project / "0001.png"
    first.write_bytes(b"image")
    scanned = recent_project_details({"path": str(project)})
    cache.store_details([scanned])
    assert cache.cached_details(project) is not None
    (project / "0002.png").write_bytes(b"image")
    assert cache.cached_details(project) is None
    assert recent_project_details({"path": str(project)})["image_count"] == 2


def test_metadata_cache_invalidated_by_settings_and_manual_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "user_config_root", lambda: tmp_path / "home")
    project = tmp_path / "dictionary"
    project.mkdir()
    settings = project / "picture_capture_settings.json"
    settings.write_text('{"dictionary_full_name":"Old"}')
    detail = recent_project_details({"path": str(project)})
    cache.store_details([detail])
    assert cache.cached_details(project) is not None
    settings.write_text('{"dictionary_full_name":"Changed and longer"}')
    assert cache.cached_details(project) is None
    detail = recent_project_details({"path": str(project)})
    cache.store_details([detail])
    cache.clear_cached_details(project)
    assert cache.cached_details(project) is None


def test_corrupt_metadata_index_fails_open(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "user_config_root", lambda: tmp_path)
    (tmp_path / "project_center_metadata.json").write_text("{invalid", encoding="utf-8")
    assert cache.read_index() == {}
