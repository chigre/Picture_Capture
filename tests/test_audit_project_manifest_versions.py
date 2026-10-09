"""Audit: malformed managed-project manifest must never crash path discovery."""
import json

import pytest

from picture_capture import project_storage as storage


@pytest.mark.parametrize("invalid", ["not-a-number", [], {}, None, "3.2", 1e999])
def test_invalid_manifest_version_returns_unmanaged(tmp_path, invalid):
    target = storage.manifest_path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "format": storage.PROJECT_FORMAT,
        "format_version": invalid,
    }), encoding="utf-8")
    assert storage.is_managed_project(tmp_path) is False
    assert storage.settings_path(tmp_path) == tmp_path / storage.LEGACY_SETTINGS_FILENAME


def test_numeric_managed_project_version_still_supported(tmp_path):
    target = storage.manifest_path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "format": storage.PROJECT_FORMAT,
        "format_version": storage.PROJECT_FORMAT_VERSION,
    }), encoding="utf-8")
    assert storage.is_managed_project(tmp_path) is True
    assert storage.settings_path(tmp_path) == storage.storage_root(tmp_path) / storage.SETTINGS_FILENAME
