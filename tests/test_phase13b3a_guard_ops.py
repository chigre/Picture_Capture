"""Phase 13B3a regression: guard-band primitive ops are an explicit dependency."""
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from PIL import Image

from picture_capture import dictionary_page_design as base
from picture_capture import dictionary_page_design_refined as refined


def test_guard_band_uses_explicit_runs_and_features(monkeypatch):
    image = Image.new("RGB", (100, 100), "white")
    monkeypatch.setattr(refined, "page_template_analysis_image", lambda source, settings, index: source)
    monkeypatch.setattr(base, "effective_page_settings", lambda settings, size, index: settings)
    monkeypatch.setattr(refined, "analysis_ink_mask", lambda gray, settings: np.ones(gray.shape, dtype=bool))
    monkeypatch.setattr(base, "_display_heads", lambda *args: [])
    calls = []

    def line_runs(strip, reference):
        calls.append("runs")
        return [(3, 14)]

    def line_feature(index, strip, y0, y1, reference, previous_end):
        calls.append("feature")
        return SimpleNamespace(
            y0=y0, y1=y1, height=y1-y0, anchor_x=None,
        )

    ops = replace(base.RAW_LAYOUT_OPS, line_runs=line_runs, line_feature=line_feature)
    transform = SimpleNamespace(canonical_image_for_analysis=lambda source: source)
    column = SimpleNamespace(
        index=0, left=10, right=85, body_mode=SimpleNamespace(),
        entry_modes=[], lines=[],
    )
    layout = SimpleNamespace(
        ordinary_line_height=12.0, body_top=15, body_bottom=80,
        transform=transform, columns=[column], indent_type="body",
    )
    assert refined._guard_band_entries(
        image, SimpleNamespace(), layout, None, [], page_index=0, ops=ops,
    ) == []
    assert calls == ["runs", "feature"]
