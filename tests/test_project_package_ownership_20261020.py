"""Ownership regression for actual Project Center and recent-registry relocation."""
from pathlib import Path
import importlib

import picture_capture

OWNERS = {
    "project_center_metadata_cache.py": ("project.metadata_cache", "details_with_cache"),
    "project_center_preview_cache.py": ("project.preview_cache", "load_project_center_previews"),
    "project_folder_launcher.py": ("project.folder_launcher", "open_project_folder"),
    "project_parameter_templates.py": ("project.parameter_templates", "capture_parameters"),
    "recent_project_locking.py": ("project.recent_locking", "recent_registry_lock"),
    "recent_projects.py": ("project.recent_projects", "load_recent_projects"),
}


def test_project_center_owners_are_physical_and_no_root_shims():
    root = Path(picture_capture.__file__).resolve().parent
    for old, (owner, symbol) in OWNERS.items():
        assert not (root / old).exists(), old
        assert (root / (owner.replace(".", "/") + ".py")).is_file(), owner
        member = getattr(importlib.import_module("picture_capture." + owner), symbol)
        assert member.__module__ == "picture_capture." + owner


def test_recent_project_registry_lock_is_canonical_owner():
    from picture_capture.project import recent_projects, recent_locking
    assert recent_projects.recent_registry_lock is recent_locking.recent_registry_lock
