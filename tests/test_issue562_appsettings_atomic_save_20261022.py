"""Regression for AppSettings crash-safe, complete-JSON atomic publication."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import pytest

import picture_capture.models as models
from picture_capture.models import AppSettings


def _temporary_artifacts(path: Path) -> list[Path]:
    return sorted(path.parent.glob(f".{path.name}.*.tmp"))


def test_settings_atomic_save_preserves_schema_unicode_and_round_trip(tmp_path: Path):
    path = tmp_path / "词典配置" / "settings.json"
    settings = AppSettings(crop_width_percent=67.5, guide_opacity=37.0)
    settings.to_json(path)

    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert "\n  " in raw
    assert payload["crop_width_percent"] == 67.5
    assert payload["guide_opacity"] == 37.0
    assert "paddle_separator_search_ratio" not in payload
    assert AppSettings.from_json(path).crop_width_percent == 67.5
    assert _temporary_artifacts(path) == []

    settings.crop_width_percent = 62.5
    settings.to_json(path)
    assert AppSettings.from_json(path).crop_width_percent == 62.5
    assert _temporary_artifacts(path) == []


@pytest.mark.parametrize("failure_point", ["fsync", "replace"])
def test_failed_atomic_settings_publication_retains_old_valid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_point: str
):
    path = tmp_path / "settings.json"
    AppSettings(crop_width_percent=44.0).to_json(path)
    original_bytes = path.read_bytes()
    called = []

    def fail_commit(*args, **kwargs):
        called.append(failure_point)
        raise OSError(f"simulated {failure_point} failure")

    monkeypatch.setattr(models.os, failure_point, fail_commit)
    with pytest.raises(OSError, match=f"simulated {failure_point} failure"):
        AppSettings(crop_width_percent=61.0).to_json(path)

    assert called == [failure_point]
    assert path.read_bytes() == original_bytes
    assert AppSettings.from_json(path).crop_width_percent == 44.0
    assert _temporary_artifacts(path) == []


def test_failed_initial_settings_save_leaves_no_invalid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "settings.json"

    def fail_replace(*args, **kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(models.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        AppSettings().to_json(path)

    assert not path.exists()
    assert _temporary_artifacts(path) == []


def test_parallel_settings_saves_publish_only_complete_payloads(tmp_path: Path):
    path = tmp_path / "settings.json"
    values = [48.0 + i for i in range(8)]

    def publish(value: float):
        AppSettings(crop_width_percent=value).to_json(path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(publish, values))

    payload = json.loads(path.read_text(encoding="utf-8"))
    reopened = AppSettings.from_json(path)
    assert payload["crop_width_percent"] in values
    assert reopened.crop_width_percent == payload["crop_width_percent"]
    assert _temporary_artifacts(path) == []
