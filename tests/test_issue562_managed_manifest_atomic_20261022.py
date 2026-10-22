"""Issue #562: managed-v2 project manifests are published atomically."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import pytest

from picture_capture import project_storage as storage


def _staged(path: Path) -> list[Path]:
    return sorted(path.parent.glob(f".{path.name}.*.tmp"))


def test_project_manifest_roundtrip_routes_managed_storage_without_moving_scan(
    tmp_path: Path,
):
    root = tmp_path / "原始词典"
    root.mkdir()
    scan = root / "scan.png"
    scan.write_bytes(b"original user-owned scan bytes")
    storage.ensure_project_storage(root, "2.14")
    manifest = storage.manifest_path(root)
    raw = manifest.read_text(encoding="utf-8")
    payload = json.loads(raw)

    assert payload["format"] == storage.PROJECT_FORMAT
    assert payload["format_version"] == storage.PROJECT_FORMAT_VERSION == 2
    assert payload["project_name"] == "原始词典"
    assert payload["storage_root"] == storage.STORAGE_DIRNAME
    assert payload["settings"] == storage.SETTINGS_FILENAME
    assert payload["created_with"] == "2.14"
    assert payload["last_opened_with"] == "2.14"
    assert storage.is_managed_project(root)
    assert storage.settings_path(root) == storage.storage_root(root) / storage.SETTINGS_FILENAME
    assert scan.read_bytes() == b"original user-owned scan bytes"
    assert "\\n  " in raw
    assert _staged(manifest) == []

    storage.ensure_project_storage(root, "2.15")
    again = json.loads(manifest.read_text(encoding="utf-8"))
    assert again["created_with"] == "2.14"
    assert again["last_opened_with"] == "2.15"
    assert storage.is_managed_project(root)
    assert _staged(manifest) == []


@pytest.mark.parametrize("fault", ["fsync", "replace"])
def test_manifest_commit_failure_keeps_prior_bytes_and_managed_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
):
    root = tmp_path / "project"
    storage.ensure_project_storage(root, "1.0")
    manifest = storage.manifest_path(root)
    original = manifest.read_bytes()
    calls: list[str] = []

    def fail(*_args, **_kwargs):
        calls.append(fault)
        raise OSError(f"injected manifest {fault} failure")

    monkeypatch.setattr(storage.os, fault, fail)
    with pytest.raises(OSError, match=f"injected manifest {fault} failure"):
        storage.ensure_project_storage(root, "1.1")
    assert calls == [fault]
    assert manifest.read_bytes() == original
    assert storage.is_managed_project(root)
    assert storage.settings_path(root) == storage.storage_root(root) / storage.SETTINGS_FILENAME
    assert _staged(manifest) == []


def test_failed_first_manifest_commit_does_not_activate_managed_v2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "legacy"
    root.mkdir()
    scan = root / "scan.png"
    scan.write_bytes(b"keep original bytes")
    manifest = storage.manifest_path(root)

    def fail_replace(*_args, **_kwargs):
        raise OSError("first manifest replace failure")

    monkeypatch.setattr(storage.os, "replace", fail_replace)
    with pytest.raises(OSError, match="first manifest replace failure"):
        storage.ensure_project_storage(root, "2.0")

    assert not manifest.exists()
    assert _staged(manifest) == []
    assert not storage.is_managed_project(root)
    assert storage.settings_path(root) == root / storage.LEGACY_SETTINGS_FILENAME
    assert scan.read_bytes() == b"keep original bytes"


def test_eight_parallel_managed_manifest_refreshes_remain_complete(tmp_path: Path):
    root = tmp_path / "project"
    storage.ensure_project_storage(root, "1.0")
    versions = [f"2.{n}" for n in range(8)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda version: storage.ensure_project_storage(root, version), versions))

    manifest = storage.manifest_path(root)
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(results) == 8
    assert all(directory == storage.storage_root(root) for directory in results)
    assert raw["format"] == storage.PROJECT_FORMAT
    assert raw["format_version"] == 2
    assert raw["created_with"] == "1.0"
    assert raw["last_opened_with"] in versions
    assert storage.is_managed_project(root)
    assert _staged(manifest) == []


def test_abandoned_fixed_manifest_tmp_does_not_pollute_new_publication(tmp_path: Path):
    root = tmp_path / "project"
    manifest = storage.manifest_path(root)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    old_staging = manifest.with_suffix(manifest.suffix + ".tmp")
    old_staging.write_text("{stale, incomplete", encoding="utf-8")

    storage.ensure_project_storage(root, "1.0")
    assert storage.is_managed_project(root)
    assert json.loads(manifest.read_text(encoding="utf-8"))["created_with"] == "1.0"
    # Never delete a pre-existing temporary file that this writer does not own.
    assert old_staging.read_text(encoding="utf-8") == "{stale, incomplete"
    assert _staged(manifest) == []
