"""Issue #562 phase 11: physical model I/O owners and legacy compatibility."""
from __future__ import annotations

import ast
import inspect
import json
import pickle
from pathlib import Path

import pytest
from PIL import Image

from picture_capture import models
from picture_capture.project import state_opening
from picture_capture.profile import settings_storage_io


def test_project_open_is_physically_owned_and_model_api_kept():
    assert "recover_incomplete_crop_publications(root)" in inspect.getsource(
        state_opening.open_project_state
    )
    assert "from ..persistence.project_storage" in inspect.getsource(
        state_opening.open_project_state
    )
    assert "return _project_state_opening.open_project_state" in inspect.getsource(
        models.ProjectState.open.__func__
    )
    assert models.ProjectState.__module__ == "picture_capture.models"
    cls = models.ProjectState
    assert pickle.loads(pickle.dumps(cls)) is cls


def test_new_project_open_recovers_storage_and_reloads_exact_saved_settings(tmp_path):
    Image.new("RGB", (24, 36), "white").save(tmp_path / "0001.png")
    from picture_capture.persistence.project_storage import qt_root, settings_path
    path = settings_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    models.AppSettings(crop_width_percent=67.25).to_json(path)

    state = models.ProjectState.open(tmp_path)
    assert [p.name for p in state.images] == ["0001.png"]
    assert state.settings.crop_width_percent == 67.25
    assert (qt_root(tmp_path) / "PaddleOCR").is_dir()
    assert (qt_root(tmp_path) / "PSW").is_dir()
    assert (qt_root(tmp_path) / "PWW").is_dir()
    assert (qt_root(tmp_path) / "PIC").is_dir()
    assert (qt_root(tmp_path) / "PicDic").is_dir()


def test_project_open_resolves_model_hooks_at_call_time(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(models, "project_page_images", lambda root: calls.append(root) or [])
    monkeypatch.setattr(models, "read_noncomment_lines", lambda path: [" patched"])
    state = models.ProjectState.open(tmp_path)
    assert calls == [tmp_path.resolve()]
    assert state.images == []


def test_settings_storage_atomic_writer_is_actual_owner_and_roundtrips(tmp_path):
    writer = inspect.getsource(settings_storage_io.write_settings_json)
    reader = inspect.getsource(settings_storage_io.read_settings_json)
    assert "NamedTemporaryFile" in writer and "os.fsync" in writer
    assert "os.replace" in writer and "temporary.unlink" in writer
    assert "migrate_app_settings_payload" in reader
    assert "return _settings_storage_io.write_settings_json" in inspect.getsource(models.AppSettings.to_json)
    assert "return _settings_storage_io.read_settings_json" in inspect.getsource(models.AppSettings.from_json.__func__)
    path = tmp_path / "词典" / "settings.json"
    models.AppSettings(crop_width_percent=53.5).to_json(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["crop_width_percent"] == 53.5
    assert models.AppSettings.from_json(path).crop_width_percent == 53.5
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_atomic_settings_writer_preserves_runtime_os_hook_and_rolls_back(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    models.AppSettings(crop_width_percent=59.0).to_json(path)
    original = path.read_bytes()
    def broken_replace(*args, **kwargs):
        raise OSError("injected publication failure")
    monkeypatch.setattr(models.os, "replace", broken_replace)
    with pytest.raises(OSError, match="injected publication failure"):
        models.AppSettings(crop_width_percent=65.0).to_json(path)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".*.tmp"))


def test_empty_nonproject_does_not_force_managed_storage(tmp_path):
    state = models.ProjectState.open(tmp_path)
    assert not state.images
    assert state.root == tmp_path.resolve()
