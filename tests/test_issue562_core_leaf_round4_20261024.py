"""Issue #562: leaf crop geometry and lemma repair keep historical hooks."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from picture_capture import processing as public_processing
from picture_capture import processing_core as core
from picture_capture import paddle_headwords as public_paddle
from picture_capture import paddle_headwords_core as paddle_core
from picture_capture.crop import entry_column_bounds
from picture_capture.ocr import lemma_repairs

PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def _sample_geometry():
    transform = SimpleNamespace(
        canonical_size=lambda size: size,
        canonical_box_to_source=lambda box, size: box,
    )
    return SimpleNamespace(
        column_starts=[10, 110],
        column_widths=[80, 80],
        x_bounds=lambda col, y0, y1: (10 + 100 * col, 10 + 100 * col),
        transform=transform,
    )


def test_physical_leaf_owners_and_historical_callable_origins():
    assert (PKG / "crop/entry_column_bounds.py").is_file()
    assert (PKG / "ocr/lemma_repairs.py").is_file()
    assert not (PKG / "entry_column_bounds.py").exists()
    assert not (PKG / "lemma_repairs.py").exists()
    assert len(list(PKG.glob("*.py"))) == 10
    assert core._entry_crop_box_for_column.__module__ == "picture_capture.processing_core"
    assert paddle_core._repair_headword_ocr.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(core._entry_crop_box_for_column).parameters) == [
        "image", "settings", "geometry", "col", "y0", "y1", "extra_left", "extra_right",
    ]
    assert list(inspect.signature(paddle_core._repair_headword_ocr).parameters) == ["text"]


def test_crop_bounds_preserve_gutter_and_canonical_coordinates():
    image = Image.new("RGB", (240, 200), "white")
    geometry = _sample_geometry()
    settings = SimpleNamespace(gutter=20)
    for col, expected in ((0, (5, 20, 100, 80)), (1, (100, 20, 195, 80))):
        got = core._entry_crop_box_for_column(image, settings, geometry, col, 20, 80)
        leaf = entry_column_bounds.entry_crop_box_for_column(
            image, settings, geometry, col, 20, 80,
            source_px_fn=core._source_px, clamp_fn=core.clamp_box,
        )
        assert got == leaf == expected


def test_crop_bounds_legacy_facade_hooks_are_live(monkeypatch):
    image = Image.new("RGB", (240, 200), "white")
    geometry = _sample_geometry()
    settings = SimpleNamespace(gutter=20)
    old_clamp = core.clamp_box
    seen = []
    def patched_clamp(box, source):
        seen.append(box)
        return old_clamp(box, source)
    monkeypatch.setattr(public_processing, "clamp_box", patched_clamp)
    assert core._entry_crop_box_for_column(image, settings, geometry, 0, 20, 80) == (5, 20, 100, 80)
    assert len(seen) == 1
    monkeypatch.setattr(public_processing, "clamp_box", old_clamp)
    original_px = core._source_px
    monkeypatch.setattr(public_processing, "_source_px", lambda x: original_px(x) + 3)
    assert core._entry_crop_box_for_column(image, settings, geometry, 0, 20, 80) != (5, 20, 100, 80)
    monkeypatch.setattr(public_processing, "_source_px", original_px)


def test_lemma_repair_parity_and_no_length_change():
    for text in (
        "", "casa", "ab6c", "a1co adj.", "a-ho.g0 s.m.",
        "a-0 adj.", "a-0 Que", "1 Que", "á1zo", "a-1 1 Que",
    ):
        old = paddle_core._repair_headword_ocr(text)
        new = lemma_repairs.repair_headword_ocr(text)
        assert old == new
        assert len(old[0]) == len(text)
    assert paddle_core._repair_headword_ocr("ab6c")[0] == "aboc"
    assert paddle_core._repair_headword_ocr("a-ho.g0 s.m.")[0] == "a-ho.go s.m."


def test_lemma_repair_public_monkeypatch_owner(monkeypatch):
    original = paddle_core._repair_headword_ocr
    monkeypatch.setattr(public_paddle, "_repair_headword_ocr", lambda text: (text, ("patched",)))
    assert paddle_core._repair_headword_ocr("word") == ("word", ("patched",))
    monkeypatch.setattr(public_paddle, "_repair_headword_ocr", original)
