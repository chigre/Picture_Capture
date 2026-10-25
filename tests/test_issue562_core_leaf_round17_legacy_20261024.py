"""Characterization of full-resolution legacy ordinary pipeline extractions.

These tests deliberately keep calls on the historical processing façade while
checking that the newly split implementation reads current patchable callbacks.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from picture_capture import processing as public_processing
from picture_capture import processing_core as core
from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary import (
    cjk_marker_reconciliation,
    legacy_page_detection,
    legacy_separator_search,
)


def _vb_kwargs():
    return dict(
        column_width=8, direction=1, row_height=5, upward_ratio=1,
        ordinary_right_divisor=1, darkness_threshold=300,
        white_threshold_high=990, white_threshold_low=700,
        whitespace_adjustment=0, top=1, x_min=0, x_max=19,
    )


def test_legacy_separator_full_white_then_brightness_fallback():
    bright = np.zeros((20, 20), dtype=np.uint16)
    bright[14, :] = 765
    y, info = core._legacy_find_separator_y(bright, 5, 15, **_vb_kwargs())
    assert y == 14
    assert info["reason"] == "vb_full_white"
    assert (y, info) == legacy_separator_search.find_separator_y(
        bright, 5, 15, **_vb_kwargs(), np_module=np,
        row_brightness_fn=core._legacy_row_brightness_1000,
        brightness_scores_fn=core.legacy_row_brightness_scores_1000,
    )

    fallback = np.zeros((20, 20), dtype=np.uint16)
    fallback[14, :] = 720
    # With all tested rows below the dark limit, full white cannot succeed.
    args = {**_vb_kwargs(), "darkness_threshold": 750}
    y, info = core._legacy_find_separator_y(fallback, 5, 15, **args)
    assert y == 14
    assert info["reason"] == "vb_brightness_fallback"
    assert info["threshold"] <= 941
    assert core._legacy_find_separator_y.__module__ == "picture_capture.processing_core"


def test_legacy_separator_uses_current_public_brightness_hook(monkeypatch):
    seen = []
    original = core._legacy_row_brightness_1000

    def patched(*args, **kwargs):
        seen.append((args, kwargs))
        return 1000

    monkeypatch.setattr(public_processing, "_legacy_row_brightness_1000", patched)
    dark = np.zeros((20, 20), dtype=np.uint16)
    dark[14, :] = 765
    core._legacy_find_separator_y(
        dark, 5, 15, **{**_vb_kwargs(), "whitespace_adjustment": 2},
    )
    assert seen, "live public callback must reach the extracted implementation"
    monkeypatch.setattr(public_processing, "_legacy_row_brightness_1000", original)


def test_legacy_edge_transform_and_historical_signatures():
    transform = SimpleNamespace(kind="identity")
    geometry = SimpleNamespace(
        transform=transform,
        x_at=lambda column, y: 17.2,
        canonical_to_source=lambda x, y: (x, y),
    )
    assert core._ordinary_source_column_edge(geometry, 0, 40) == (17, 1)
    assert legacy_page_detection.source_column_edge(geometry, 0, 40) == (17, 1)
    transform.kind = "mirror_x"
    geometry.canonical_to_source = lambda x, y: (100 - x, y)
    assert core._ordinary_source_column_edge(geometry, 0, 40) == (83, -1)
    transform.kind = "rotate"
    import pytest
    with pytest.raises(RuntimeError, match="OCR"):
        core._ordinary_source_column_edge(geometry, 0, 40)

    assert list(inspect.signature(core._detect_entries_left_edge).parameters) == [
        "image", "settings", "page_sections",
    ]
    assert core._ordinary_source_column_edge.__module__ == "picture_capture.processing_core"


def test_full_scan_live_dependencies_and_root_inventory(monkeypatch):
    package = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(package.glob("*.py"))) == 9
    for relative in (
        "ordinary/legacy_separator_search.py",
        "ordinary/legacy_page_detection.py",
        "ordinary/cjk_marker_reconciliation.py",
    ):
        assert (package / relative).is_file()

    seen = []
    def spy(image, settings, page_sections=None, *, deps):
        seen.append(deps)
        return ["sentinel"], "geometry"

    patched_edge = lambda geometry, column, y: (101, 1)
    monkeypatch.setattr(legacy_page_detection, "detect_entries_left_edge", spy)
    monkeypatch.setattr(public_processing, "_ordinary_source_column_edge", patched_edge)
    value = core._detect_entries_left_edge(object(), AppSettings())
    assert value == (["sentinel"], "geometry")
    assert seen and seen[0]["_ordinary_source_column_edge"] is patched_edge
    assert seen[0]["_legacy_find_separator_y"] is core._legacy_find_separator_y


def test_cjk_guard_and_live_callback_delegation(monkeypatch):
    settings = AppSettings()
    settings.layout_writing_mode = "vertical-rl"
    one = Entry(word="", x=20, y=30)
    image = Image.new("RGB", (60, 70), "white")
    for fn in (
        core._collapse_ordinary_oversized_cjk_split_markers,
        core._recover_ordinary_oversized_cjk_missing_markers,
    ):
        result = fn(image, [one], object(), settings)
        assert result == [one]
        assert fn.__module__ == "picture_capture.processing_core"

    seen = []
    def spy(image, entries, geometry, settings, *, deps):
        seen.append(deps)
        return entries

    monkeypatch.setattr(
        cjk_marker_reconciliation, "recover_oversized_cjk_missing_markers", spy,
    )
    marker_edge = lambda geometry, col, y: (45, 1)
    monkeypatch.setattr(public_processing, "_ordinary_source_column_edge", marker_edge)
    assert core._recover_ordinary_oversized_cjk_missing_markers(
        image, [one], object(), settings,
    ) == [one]
    assert seen[0]["_ordinary_source_column_edge"] is marker_edge
