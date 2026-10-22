"""#562: one grouped physical Layout detector and row-cache ownership."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from picture_capture.layout import detection, rows_cache

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_two_layout_owners_are_real_without_root_shims() -> None:
    for retired, owner, symbol in (
        ("layout_detection", "detection", "detect_layout_parameters"),
        ("layout_rows_cache", "rows_cache", "load_layout_rows_cache"),
    ):
        assert not (ROOT / (retired + ".py")).exists()
        assert (ROOT / "layout" / (owner + ".py")).is_file()
        assert importlib.util.find_spec("picture_capture." + retired) is None
        assert importlib.util.find_spec("picture_capture.layout." + owner) is not None
        mod = {"detection": detection, "rows_cache": rows_cache}[owner]
        assert callable(getattr(mod, symbol))


def test_layout_detector_and_cache_keep_single_module_owners() -> None:
    assert detection.detect_layout_parameters.__module__ == "picture_capture.layout.detection"
    assert rows_cache.load_layout_rows_cache.__module__ == "picture_capture.layout.rows_cache"
    assert callable(detection.clear_layout_estimate_cache)
    assert callable(rows_cache.resolve_physical_rows_layout)
