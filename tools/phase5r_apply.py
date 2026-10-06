from __future__ import annotations

from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(rel: str, old: str, new: str) -> None:
    text = read(rel)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{rel}: expected exactly one migration anchor, found {count}")
    write(rel, text.replace(old, new, 1))


helper = dedent(r'''\
from __future__ import annotations

"""Observed character-height recovery for fallback Layout estimates.

Dense dictionary pages can make layout text boxes merge vertically, leaving the
reliable detector on its ``fallback=character_height`` projection path with an
underestimated page-height heuristic.  This module keeps the established
physical-row measurement as ordinary static logic: only an estimate already
marked for that fallback is eligible, and only ``character_height`` plus method
provenance may change.
"""

from dataclasses import replace
from typing import Any

import numpy as np
from PIL import Image, ImageOps


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    values = np.asarray(mask, dtype=bool)
    if values.ndim != 1 or values.size == 0:
        return []
    padded = np.pad(values.astype(np.int8), (1, 1), constant_values=0)
    changes = np.diff(padded)
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)
    return [(int(a), int(b)) for a, b in zip(starts, ends) if b > a]


def _fill_tiny_vertical_gaps(active: np.ndarray, maximum_gap: int = 1) -> np.ndarray:
    result = np.asarray(active, dtype=bool).copy()
    if maximum_gap <= 0 or result.size < 3:
        return result
    false_runs = _runs(~result)
    for start, end in false_runs:
        if start > 0 and end < result.size and end - start <= maximum_gap:
            result[start:end] = True
    return result


def observed_character_height(
    image: Image.Image,
    settings: Any,
    estimate: Any,
    backend: Any,
) -> tuple[int | None, dict[str, float | int]]:
    """Estimate ordinary glyph-ink height from physical row-projection bands."""
    source = image.convert("RGB")
    gray = np.asarray(ImageOps.grayscale(source), dtype=np.uint8)
    ink = backend.analysis_ink_mask(gray, settings)
    if ink.ndim != 2 or ink.size == 0 or not np.any(ink):
        return None, {"samples": 0}

    height, width = ink.shape
    current = max(1, int(getattr(estimate, "character_height", 1) or 1))
    top = max(0, min(height - 1, int(getattr(estimate, "start_y", 0) or 0)))
    bottom = max(top + 1, min(height, int(getattr(estimate, "bottom_y", height) or height)))
    column_width = max(24, int(getattr(estimate, "column_width", width) or width))
    starts = list(getattr(estimate, "column_starts", ()) or ())
    if not starts:
        count = max(1, int(getattr(estimate, "columns", 1) or 1))
        x0 = max(0, int(getattr(estimate, "manual_x", 0) or 0))
        gutter = max(0, int(getattr(estimate, "gutter", 0) or 0))
        starts = [x0 + index * (column_width + gutter) for index in range(count)]

    # Same broad leading domain used by Page Design.  It is wide enough to make
    # row presence robust while still avoiding ragged line endings.
    leading_width = max(
        24,
        min(column_width, max(round(column_width * 0.42), round(current * 7.0), 96)),
    )

    lower = max(6, int(round(current * 0.65)))
    upper = max(lower + 2, int(round(current * 2.10)))
    heights: list[int] = []
    for raw_left in starts:
        left = max(0, min(width - 1, int(raw_left)))
        right = max(left + 1, min(width, left + leading_width))
        strip = ink[top:bottom, left:right]
        if strip.size == 0:
            continue
        row_ink = np.asarray(strip, dtype=np.uint8).sum(axis=1)
        threshold = max(2, int(round(strip.shape[1] * 0.003)))
        active = _fill_tiny_vertical_gaps(row_ink >= threshold, 1)
        for y0, y1 in _runs(active):
            run_height = int(y1 - y0)
            if lower <= run_height <= upper:
                heights.append(run_height)

    if len(heights) < 8:
        return None, {"samples": len(heights)}

    values = np.asarray(heights, dtype=float)
    center = float(np.median(values))
    deviation = np.abs(values - center)
    mad = float(np.median(deviation)) if deviation.size else 0.0
    tolerance = max(2.0, 3.5 * mad)
    kept = values[deviation <= tolerance]
    if kept.size < 8:
        return None, {"samples": int(kept.size), "median": center, "mad": mad}

    center = float(np.median(kept))
    q10, q90 = (float(v) for v in np.percentile(kept, [10, 90]))
    spread = q90 - q10
    if center <= 0 or spread > max(4.0, center * 0.18):
        return None, {
            "samples": int(kept.size),
            "median": center,
            "spread": spread,
        }

    return max(1, int(round(center))), {
        "samples": int(kept.size),
        "median": center,
        "spread": spread,
    }


def apply_character_height_fallback(
    image: Image.Image,
    settings: Any,
    estimate: Any,
    backend: Any,
) -> Any:
    """Apply the established fallback correction without mutating raw estimates."""
    method = str(getattr(estimate, "method", "") or "")
    if "fallback=character_height" not in method:
        return estimate

    observed, stats = observed_character_height(
        image,
        settings,
        estimate,
        backend,
    )
    if observed is None:
        return estimate

    current = max(1, int(getattr(estimate, "character_height", 1) or 1))
    ratio = float(observed) / float(current)
    # Small differences are harmless and should not churn page parameters.
    if 0.82 <= ratio <= 1.22:
        return estimate

    updated = replace(estimate, character_height=int(observed))
    updated.method = (
        f"{method}+observed_character_height={int(observed)}"
        f"(n={int(stats.get('samples', 0))})"
    )
    return updated


__all__ = ["apply_character_height_fallback", "observed_character_height"]
''')
write("src/picture_capture/layout_character_height.py", helper)

replace_once(
    "src/picture_capture/layout_detection.py",
    dedent('''\
def detect_layout_parameters(image, settings):
    from .layout_reliability import detect_layout_parameters_reliable

    analysis_image = build_analysis_image(image, settings)
    key = _layout_estimate_cache_key(analysis_image, settings)
    cached = _LAYOUT_ESTIMATE_CACHE.get(key)
    if cached is not None:
        _LAYOUT_ESTIMATE_CACHE.move_to_end(key)
        return cached

    result = detect_layout_parameters_reliable(
        analysis_image, settings, sys.modules[__name__]
    )
    _LAYOUT_ESTIMATE_CACHE[key] = result
    _LAYOUT_ESTIMATE_CACHE.move_to_end(key)
    while len(_LAYOUT_ESTIMATE_CACHE) > _LAYOUT_ESTIMATE_CACHE_LIMIT:
        _LAYOUT_ESTIMATE_CACHE.popitem(last=False)
    return result
'''),
    dedent('''\
def detect_layout_parameters(image, settings):
    from .layout_character_height import apply_character_height_fallback
    from .layout_reliability import detect_layout_parameters_reliable

    analysis_image = build_analysis_image(image, settings)
    key = _layout_estimate_cache_key(analysis_image, settings)
    raw = _LAYOUT_ESTIMATE_CACHE.get(key)
    if raw is not None:
        _LAYOUT_ESTIMATE_CACHE.move_to_end(key)
    else:
        raw = detect_layout_parameters_reliable(
            analysis_image, settings, sys.modules[__name__]
        )
        _LAYOUT_ESTIMATE_CACHE[key] = raw
        _LAYOUT_ESTIMATE_CACHE.move_to_end(key)
        while len(_LAYOUT_ESTIMATE_CACHE) > _LAYOUT_ESTIMATE_CACHE_LIMIT:
            _LAYOUT_ESTIMATE_CACHE.popitem(last=False)

    # Preserve the historical two-layer cache contract: the reliable/raw
    # estimate is cached, while observed character-height correction is replayed
    # after every cache lookup and is never written back into the raw cache.
    return apply_character_height_fallback(
        image,
        settings,
        raw,
        sys.modules[__name__],
    )
'''),
)

replace_once(
    "src/picture_capture/bootstrap/core.py",
    dedent('''\
    # Must precede consumers that capture the detector callable by value.
    from ..layout_character_height_runtime import (
        install_character_height_fallback_runtime,
    )

    install_character_height_fallback_runtime()

'''),
    dedent('''\
    # Character-height fallback is static inside layout_detection, so consumers
    # that import the detector by value no longer depend on installer ordering.

'''),
)

replace_once(
    "src/picture_capture/bootstrap/gui.py",
    dedent('''\
    # Character-height recovery must be installed before Page Design/policy
    # modules import detect_layout_parameters by value.  Core composition has
    # already established it; this local call remains as an idempotent ordering
    # guard while the legacy runtime chain is being retired.
    from ..layout_character_height_runtime import (
        install_character_height_fallback_runtime,
    )

    install_character_height_fallback_runtime()

'''),
    dedent('''\
    # Character-height fallback is now static in layout_detection; Page Design
    # and policy imports no longer depend on a local installer ordering guard.

'''),
)

replace_once(
    "src/picture_capture/unlined_physical_rows_resolver.py",
    "    # Escalate geometry only.  These installers are required because an unlined\n"
    "    # worker is spawned independently of the GUI launcher on Windows/macOS.\n"
    "    from .layout_character_height_runtime import install_character_height_fallback_runtime\n"
    "    from .layout_column_drift_runtime import install_layout_column_drift_runtime\n"
    "    from .layout_line_start_refinement import install_robust_line_starts\n"
    "    from .layout_physical_indent import install_physical_indent_inference\n\n"
    "    install_character_height_fallback_runtime()\n"
    "    install_robust_line_starts()\n",
    "    # Escalate geometry only. Character-height fallback is static in the\n"
    "    # detector; the remaining installers are still required because an\n"
    "    # unlined worker is spawned independently of the GUI launcher.\n"
    "    from .layout_column_drift_runtime import install_layout_column_drift_runtime\n"
    "    from .layout_line_start_refinement import install_robust_line_starts\n"
    "    from .layout_physical_indent import install_physical_indent_inference\n\n"
    "    install_robust_line_starts()\n",
)

replace_once(
    "scripts/architecture_guard.py",
    '    "layout_character_height_runtime.py",\n',
    "",
)

replace_once(
    "tests/test_core_bootstrap.py",
    "    character_height = source.index(\"install_character_height_fallback_runtime()\")\n"
    "    live_binding = source.index(\"install_live_layout_detector_binding()\")\n"
    "    large_head = source.index(\"install_ordinary_large_head_runtime()\")\n"
    "    processing_import = source.index(\"from .. import processing as processing_module\")\n\n"
    "    assert character_height < live_binding < large_head < processing_import\n",
    "    live_binding = source.index(\"install_live_layout_detector_binding()\")\n"
    "    large_head = source.index(\"install_ordinary_large_head_runtime()\")\n"
    "    processing_import = source.index(\"from .. import processing as processing_module\")\n\n"
    "    assert live_binding < large_head < processing_import\n"
    "    assert \"install_character_height_fallback_runtime\" not in source\n",
)
replace_once(
    "tests/test_core_bootstrap.py",
    '        "install_character_height_fallback_runtime",\n',
    "",
)

character_test = dedent(r'''\
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
''')
write("tests/test_layout_character_height_fallback_runtime.py", character_test)

runtime_path = ROOT / "src/picture_capture/layout_character_height_runtime.py"
if not runtime_path.exists():
    raise RuntimeError("legacy character-height runtime missing")
runtime_path.unlink()

# Fail closed if production still imports the retired runtime/installer.
for path in (ROOT / "src/picture_capture").rglob("*.py"):
    text = path.read_text(encoding="utf-8")
    if "layout_character_height_runtime" in text:
        raise RuntimeError(f"retired runtime reference remains in {path.relative_to(ROOT)}")
    if "install_character_height_fallback_runtime" in text:
        raise RuntimeError(f"retired installer reference remains in {path.relative_to(ROOT)}")

print("Phase 5R migration applied")
