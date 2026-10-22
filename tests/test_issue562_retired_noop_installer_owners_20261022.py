"""Issue #562: two retired no-op installers are physical domain leafs, not root files."""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace


def test_retired_imports_have_one_physical_domain_owner_without_root_shims():
    from picture_capture.layout import detector_live_binding
    from picture_capture.ui.settings import legacy_help_restore

    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert not (root / "layout_detector_live_binding.py").exists()
    assert not (root / "settings_help_restore.py").exists()
    assert (root / "layout/detector_live_binding.py").is_file()
    assert (root / "ui/settings/legacy_help_restore.py").is_file()
    assert detector_live_binding.__file__ == str(root / "layout/detector_live_binding.py")
    assert legacy_help_restore.__file__ == str(root / "ui/settings/legacy_help_restore.py")
    assert importlib.util.find_spec("picture_capture.layout_detector_live_binding") is None
    assert importlib.util.find_spec("picture_capture.settings_help_restore") is None


def test_layout_install_noop_never_changes_live_detector_or_policy():
    from picture_capture.layout import detector_live_binding
    from picture_capture.design import layout_policy
    from picture_capture import layout_detection

    original = layout_policy.detect_layout_parameters
    assert detector_live_binding.install_live_layout_detector_binding() is None
    assert layout_policy.detect_layout_parameters is original

    sentinel = object()
    from unittest.mock import patch
    with patch.object(layout_detection, "detect_layout_parameters", return_value=sentinel):
        assert layout_policy.detect_layout_parameters(None, None) is sentinel


def test_settings_help_noop_does_not_mutate_application_or_widget_classes():
    from picture_capture.ui.settings.legacy_help_restore import install_settings_help_restore

    class FakeApp:
        value = object()

    app = SimpleNamespace(SettingsDialog=FakeApp)
    before = dict(FakeApp.__dict__)
    assert install_settings_help_restore(app) is None
    assert dict(FakeApp.__dict__) == before


def test_leaf_first_imports_no_gui_bootstrap_and_no_root_alias_modules():
    script = """
import importlib
import sys
layout = importlib.import_module("picture_capture.layout.detector_live_binding")
settings = importlib.import_module("picture_capture.ui.settings.legacy_help_restore")
assert 'picture_capture.app' not in sys.modules
assert 'picture_capture.layout_detector_live_binding' not in sys.modules
assert 'picture_capture.settings_help_restore' not in sys.modules
assert layout.install_live_layout_detector_binding() is None
assert settings.install_settings_help_restore(object()) is None
"""
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
