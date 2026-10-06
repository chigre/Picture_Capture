\
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from picture_capture.layout_character_height import (
    apply_character_height_fallback,
    observed_character_height,
)
from picture_capture.layout_detection import LayoutEstimate


class _Backend:
    @staticmethod
    def analysis_ink_mask(gray: np.ndarray, _settings: object) -> np.ndarray:
        return np.asarray(gray, dtype=np.uint8) < 128


def _fallback_estimate(*, character_height: int = 37, method: str = "projection+fallback=character_height") -> LayoutEstimate:
    return LayoutEstimate(
        columns=1,
        start_y=0,
        column_width=220,
        gutter=0,
        manual_x=20,
        bottom_y=720,
        character_height=character_height,
        row_padding=2,
        source_boxes=0,
        method=method,
        column_starts=(20,),
    )


def _dense_rows_image() -> Image.Image:
    image = Image.new("RGB", (320, 720), "white")
    draw = ImageDraw.Draw(image)
    for top in range(20, 660, 82):
        draw.rectangle((30, top, 190, top + 57), fill="black")
    return image


def test_observed_character_height_recovers_real_row_ink_height() -> None:
    image = _dense_rows_image()
    observed, stats = observed_character_height(
        image,
        SimpleNamespace(),
        _fallback_estimate(),
        _Backend,
    )

    assert observed == 58
    assert int(stats["samples"]) >= 8
    assert float(stats["spread"]) <= 4.0
    image.close()


def test_observed_character_height_rejects_sparse_ambiguous_page() -> None:
    image = Image.new("RGB", (320, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 20, 190, 77), fill="black")
    draw.rectangle((30, 120, 190, 177), fill="black")

    estimate = replace(_fallback_estimate(), bottom_y=300)
    observed, stats = observed_character_height(
        image,
        SimpleNamespace(),
        estimate,
        _Backend,
    )

    assert observed is None
    assert int(stats["samples"]) < 8
    image.close()


def test_static_fallback_updates_only_character_height_and_method_provenance() -> None:
    image = _dense_rows_image()
    raw = _fallback_estimate()

    updated = apply_character_height_fallback(
        image,
        SimpleNamespace(),
        raw,
        _Backend,
    )

    assert updated is not raw
    assert raw.character_height == 37
    assert updated.character_height == 58
    assert updated.columns == raw.columns
    assert updated.column_starts == raw.column_starts
    assert updated.method.startswith(raw.method + "+observed_character_height=58(n=")
    assert updated.method.endswith(")")
    image.close()


def test_static_fallback_leaves_non_fallback_estimate_by_identity() -> None:
    image = Image.new("RGB", (32, 32), "white")
    raw = _fallback_estimate(method="paddle")
    assert apply_character_height_fallback(image, SimpleNamespace(), raw, _Backend) is raw
    image.close()


def test_layout_detection_caches_raw_estimate_and_reapplies_fallback(monkeypatch) -> None:
    from picture_capture import layout_character_height, layout_detection, layout_reliability
    from picture_capture.models import AppSettings

    image = Image.new("RGB", (80, 120), "white")
    settings = AppSettings()
    raw = _fallback_estimate()
    reliable_calls: list[int] = []
    apply_calls: list[int] = []

    def fake_reliable(_analysis_image, _settings, _backend):
        reliable_calls.append(1)
        return raw

    def fake_apply(original_image, _settings, estimate, _backend):
        assert original_image is image
        assert estimate is raw
        apply_calls.append(1)
        return replace(estimate, character_height=60 + len(apply_calls))

    monkeypatch.setattr(layout_reliability, "detect_layout_parameters_reliable", fake_reliable)
    monkeypatch.setattr(layout_character_height, "apply_character_height_fallback", fake_apply)
    layout_detection.clear_layout_estimate_cache()
    try:
        first = layout_detection.detect_layout_parameters(image, settings)
        second = layout_detection.detect_layout_parameters(image, settings)

        assert len(reliable_calls) == 1
        assert len(apply_calls) == 2
        assert first.character_height == 61
        assert second.character_height == 62
        assert raw.character_height == 37
        assert len(layout_detection._LAYOUT_ESTIMATE_CACHE) == 1
        assert next(iter(layout_detection._LAYOUT_ESTIMATE_CACHE.values())) is raw
    finally:
        layout_detection.clear_layout_estimate_cache()
        image.close()


def test_character_height_fallback_has_static_ownership_without_installer() -> None:
    root = Path(__file__).resolve().parents[1]
    package_init = (root / "src/picture_capture/__init__.py").read_text(encoding="utf-8")
    detector = (root / "src/picture_capture/layout_detection.py").read_text(encoding="utf-8")
    core = (root / "src/picture_capture/bootstrap/core.py").read_text(encoding="utf-8")
    gui = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")
    worker = (root / "src/picture_capture/bootstrap/worker.py").read_text(encoding="utf-8")
    unlined = (root / "src/picture_capture/unlined_physical_rows_resolver.py").read_text(encoding="utf-8")

    assert "install_character_height_fallback_runtime" not in package_init
    assert "install_character_height_fallback_runtime" not in core
    assert "install_character_height_fallback_runtime" not in gui
    assert "install_character_height_fallback_runtime" not in worker
    assert "install_character_height_fallback_runtime" not in unlined
    assert "layout_character_height_runtime" not in core
    assert "layout_character_height_runtime" not in gui
    assert "layout_character_height_runtime" not in unlined

    # Static ownership lives at the detector return boundary, after raw cache
    # lookup/fill; consumers may safely import this callable by value.
    assert "apply_character_height_fallback" in detector
    assert detector.index("_LAYOUT_ESTIMATE_CACHE.get(key)") < detector.index(
        "return apply_character_height_fallback("
    )
    assert "core_services = build_core_services()" in worker
