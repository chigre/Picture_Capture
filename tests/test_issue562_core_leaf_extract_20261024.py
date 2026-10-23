"""Issue #562: non-persistent core leaves preserve old call-time patch contracts."""
from __future__ import annotations

import inspect
from pathlib import Path

from picture_capture import processing as processing_public
from picture_capture import processing_core as processing_core
from picture_capture import paddle_headwords as headwords_public
from picture_capture import paddle_headwords_core as headwords_core
from picture_capture.crop import polygon_geometry, worker_policy
from picture_capture.ocr import headword_normalization


PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_core_leaves_have_real_package_owners_without_root_compat_stubs():
    assert (PKG / "crop" / "polygon_geometry.py").is_file()
    assert (PKG / "crop" / "worker_policy.py").is_file()
    assert (PKG / "ocr" / "headword_normalization.py").is_file()
    assert not (PKG / "polygon_geometry.py").exists()
    assert not (PKG / "worker_policy.py").exists()
    assert not (PKG / "headword_normalization.py").exists()
    assert len(list(PKG.glob("*.py"))) == 10


def test_core_legacy_callable_module_paths_and_signatures():
    assert processing_core.polygon_intersects_box.__module__ == "picture_capture.processing_core"
    assert processing_core.resolve_crop_worker_count.__module__ == "picture_capture.processing_core"
    assert headwords_core.normalize_headword.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(headwords_core.normalize_headword).parameters) == [
        "text", "remove_syllable_separators",
    ]
    assert list(inspect.signature(processing_core.resolve_crop_worker_count).parameters) == [
        "configured", "cpu_count",
    ]


def test_polygon_cases_and_legacy_import_forwarders():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    for box, expected in (
        ((2, 2, 4, 4), True),
        ((8, 8, 12, 12), True),
        ((20, 20, 30, 30), False),
    ):
        assert polygon_geometry.polygon_intersects_box(square, box) is expected
        assert processing_core.polygon_intersects_box(square, box) is expected
        assert processing_public.polygon_intersects_box(square, box) is expected
    assert processing_core.polygon_fully_inside_boxes([(2, 2)], [(0, 0, 3, 3)])
    assert processing_core._box_intersection_area((0, 0, 4, 4), (2, 2, 5, 5)) == 4
    assert not processing_core.polygon_fully_inside_boxes([], [(0, 0, 3, 3)])


def test_legacy_polygon_runtime_patch_is_read_on_each_call(monkeypatch):
    points = [(100, 100), (110, 100), (105, 110)]
    box = (0, 0, 10, 10)
    assert not processing_core.polygon_intersects_box(points, box)
    monkeypatch.setattr(processing_public, "_segments_intersect", lambda *args: True)
    assert processing_core.polygon_intersects_box(points, box)

    seen = []
    original = processing_core._orientation
    def spy(*args):
        seen.append(args)
        return original(*args)
    monkeypatch.setattr(processing_public, "_orientation", spy)
    assert processing_core._segments_intersect((0, 0), (2, 2), (0, 2), (2, 0))
    assert len(seen) == 4
    monkeypatch.setattr(processing_public, "_point_in_rect", lambda *args: False)
    assert not processing_core.polygon_fully_inside_boxes([(1, 1)], [(0, 0, 2, 2)])


def test_headword_normalization_parity_and_public_patch(monkeypatch):
    for word in ("casa", "pre·fijo", "-aico", "agro-", "ma-ri-po-sa", "café"):
        assert headwords_core.normalize_headword(word) == headword_normalization.normalize_headword(
            word, syllable_separators=headwords_core._SYLLABLE_SEPARATORS,
        )
    assert headwords_core.normalize_headword("-aico") == "-aico"
    assert headwords_core.normalize_headword("agro-") == "agro-"
    assert headwords_core.normalize_headword("pre·fijo") == "prefijo"
    monkeypatch.setattr(headwords_public, "_SYLLABLE_SEPARATORS", "^")
    assert headwords_core.normalize_headword("con^tra") == "contra"


def test_worker_policy_equivalence_and_os_monkeypatch(monkeypatch):
    for cpus in (1, 2, 3, 4, 16, 64):
        for configured in (0, 1, 3, 8, 100, None, "bad"):
            expected = worker_policy.resolve_crop_worker_count(configured, cpus)
            assert processing_core.resolve_crop_worker_count(configured, cpus) == expected
    monkeypatch.setattr(processing_public.os, "cpu_count", lambda: 64)
    assert processing_core.resolve_crop_worker_count() == 4
    assert processing_core.resolve_crop_worker_count(configured=16) == 8
