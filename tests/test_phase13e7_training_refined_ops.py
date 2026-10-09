"""Phase 13E: training Page Design diagnostics keep raw geometry with explicit physical ops."""
from PIL import Image, ImageDraw

from picture_capture import dictionary_page_design as base
from picture_capture import dictionary_page_design_refined as refined
from picture_capture import layout_line_start_refinement as robust
from picture_capture import layout_physical_indent as physical
from picture_capture.models import AppSettings


def _page():
    image = Image.new("RGB", (260, 190), "white")
    draw = ImageDraw.Draw(image)
    for i in range(7):
        y = 10 + i * 22
        draw.rectangle((18, y, 30, y + 10), fill="black")
        draw.rectangle((47, y, 105, y + 10), fill="black")
    return image, AppSettings(
        columns=1, manual_x=14, column_width=170,
        start_y=5, character_height=13, ordinary_auto_layout=False,
    )


def _signature(result):
    layout = result.layout
    return (
        layout.body_top, layout.body_bottom, layout.reason, layout.reliable,
        [(c.left, c.right, [(line.y0, line.y1, line.first_x, line.anchor_x, line.role)
                             for line in c.lines]) for c in layout.columns],
        [(entry.x, entry.y) for entry in result.entries],
    )


def test_refined_explicit_physical_matches_historical_installed_hooks(monkeypatch):
    image, settings = _page()
    try:
        explicit = refined.detect_entries_from_page_design(
            image, settings, ops=physical.explicit_physical_layout_ops(),
        )
        monkeypatch.setattr(base, "_line_runs", physical.projection_line_runs)
        monkeypatch.setattr(
            physical, "_BASE_LINE_FEATURE",
            robust.compose_robust_line_feature(base.RAW_LAYOUT_OPS.line_feature),
        )
        monkeypatch.setattr(base, "_line_feature", physical.physical_line_feature)
        monkeypatch.setattr(base, "_indent_modes", physical.physical_indent_modes)
        monkeypatch.setattr(base, "_assign_indent_semantics", physical.assign_binary_roles)
        legacy = refined.detect_entries_from_page_design(image, settings)
        assert _signature(explicit) == _signature(legacy)
    finally:
        image.close()


def test_training_diagnostic_explicit_ops_are_present_without_public_policy_rebinding():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "src" / "picture_capture"
              / "training_export_v3.py").read_text(encoding="utf-8")
    assert "ops=explicit_physical_layout_ops()" in source
    assert "from .dictionary_page_design_refined import" in source
