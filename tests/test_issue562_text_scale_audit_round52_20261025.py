"""Issue #562 Round 52: paired text-scale audit's real physical owner."""
from __future__ import annotations

import ast
import inspect
import pickle
from pathlib import Path

import numpy as np
import pytest

from picture_capture.preprocess import geometry, text_scale_audit


ROOT = Path(__file__).resolve().parents[1]


def _quads(count: int = 16, *, vertical: bool = False):
    w, h = (8.0, 22.0) if vertical else (20.0, 9.0)
    return [
        np.asarray(
            [[x, y], [x+w, y], [x+w, y+h], [x, y+h]],
            dtype=float,
        )
        for i in range(count)
        for x, y in [(20.0 + (i % 4) * 70.0, 35.0 + (i // 4) * 55.0)]
    ]


def _stretch_horizontal(polygons, magnitudes):
    output = []
    for polygon, gain in zip(polygons, magnitudes):
        mapped = polygon.copy()
        x0 = float(mapped[0, 0])
        mapped[:, 0] = x0 + (mapped[:, 0] - x0) * gain
        output.append(mapped)
    return output


def test_scale_audit_owner_contains_real_math_and_has_no_backwards_import():
    source = (ROOT / "src/picture_capture/preprocess/text_scale_audit.py").read_text(encoding="utf-8")
    geometry_path = ROOT / "src/picture_capture/preprocess/geometry.py"
    facade = geometry_path.read_text(encoding="utf-8")
    definitions = {
        node.name: node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
    }
    assert {"polygon_inline_cross_size", "robust_spatial_gradient_ratio",
            "audit_text_scale_stability"} <= definitions.keys()
    assert "np.linalg.lstsq" in source
    assert "np.quantile" in source
    assert "picture_capture.app" not in source
    assert "from .geometry import" not in source
    assert "tkinter" not in source
    for name in (
        "_polygon_inline_cross_size", "_robust_spatial_gradient_ratio",
        "audit_text_scale_stability",
    ):
        assert f"def {name}(" in facade
        assert Path(getattr(geometry, name).__code__.co_filename).resolve() == geometry_path.resolve()
    assert "_text_scale_audit.audit_text_scale_stability(" in facade


def test_insufficient_and_uniform_scale_preserve_historical_verdict_dataclass():
    original = _quads()
    few = geometry.audit_text_scale_stability(original[:9], original[:9], (400, 400))
    assert type(few) is geometry.TextScaleStabilityAudit
    assert few.sample_count == 9
    assert few.verdict == "insufficient"

    identity = geometry.audit_text_scale_stability(original, original, (400, 400))
    assert identity.verdict == "stable" and identity.sample_count == 16
    assert identity.inline_ratio_median == pytest.approx(1.0)
    assert identity.cross_ratio_median == pytest.approx(1.0)

    uniform = geometry.audit_text_scale_stability(
        original, _stretch_horizontal(original, [1.1] * 16), (400, 400),
    )
    assert uniform.verdict == "worse"
    assert uniform.inline_ratio_median == pytest.approx(1.1)
    assert uniform.anisotropy_p95_ratio == pytest.approx(0.1)
    assert pickle.loads(pickle.dumps(uniform)) == uniform
    assert type(pickle.loads(pickle.dumps(uniform))) is geometry.TextScaleStabilityAudit


def test_spatially_varying_scale_is_rejected_but_safe_thresholds_patch_live(monkeypatch):
    original = _quads()
    varying = _stretch_horizontal(original, [1.0 + 0.15 * i / 15 for i in range(16)])
    risky = geometry.audit_text_scale_stability(original, varying, (400, 400))
    assert risky.verdict == "worse"
    assert risky.inline_ratio_span_ratio > geometry.TEXT_SCALE_INLINE_SPAN_MAX

    mild = _stretch_horizontal(original, [1.1] * 16)
    monkeypatch.setattr(geometry, "TEXT_SCALE_ANISOTROPY_P95_MAX", 0.20)
    accepted = geometry.audit_text_scale_stability(original, mild, (400, 400))
    assert accepted.verdict == "stable"


def test_vertical_script_and_invalid_polygon_samples():
    original = _quads(vertical=True)
    result = geometry.audit_text_scale_stability(
        original, original, (400, 400), writing_mode="vertical-rl",
    )
    assert result.verdict == "stable"
    np.testing.assert_allclose(
        [result.inline_ratio_median, result.cross_ratio_median], [1.0, 1.0],
    )
    malformed = [np.asarray([[0, 0], [2, 2]], dtype=float)] * 16
    bad = geometry.audit_text_scale_stability(malformed, malformed, (400, 400))
    assert bad.sample_count == 0 and bad.verdict == "insufficient"


def test_original_geometry_helpers_are_passed_live_by_public_audit(monkeypatch):
    quads = _quads()
    calls = []
    original = geometry._polygon_inline_cross_size
    def spy(polygon, *, writing_mode):
        calls.append(writing_mode)
        return original(polygon, writing_mode=writing_mode)
    monkeypatch.setattr(geometry, "_polygon_inline_cross_size", spy)
    result = geometry.audit_text_scale_stability(quads, quads, (400, 400))
    assert result.verdict == "stable"
    assert calls == ["horizontal-tb"] * 32
    assert list(inspect.signature(geometry.audit_text_scale_stability).parameters) == [
        "before_polygons", "after_polygons", "size", "writing_mode",
    ]
