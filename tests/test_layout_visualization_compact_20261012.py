"""Compact Layout is readable by default; full evidence lives in the inspector."""
from __future__ import annotations

from types import SimpleNamespace

import picture_capture.layout_visualization_ui as base
import picture_capture.layout_visualization_summary as summary
import picture_capture.layout_visualization_ui_v3 as controls
from picture_capture.ordinary_unified_visualization import (
    draw_unified_candidate_overlay,
)


class _Flag:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Canvas:
    def __init__(self):
        self.text = []
        self.lines = []
        self.rectangles = []
        self.bindings = []

    def delete(self, *_args):
        pass

    def create_line(self, *coords, **kwargs):
        self.lines.append((coords, kwargs))
        return len(self.lines)

    def create_text(self, *coords, **kwargs):
        self.text.append((coords, kwargs))
        return len(self.text)

    def bbox(self, _id):
        return (0, 0, 100, 20)

    def create_rectangle(self, *coords, **kwargs):
        self.rectangles.append((coords, kwargs))
        return len(self.rectangles)

    def tag_lower(self, *args):
        pass

    def tag_raise(self, *args):
        pass

    def tag_bind(self, *args):
        self.bindings.append(args)


class _Path:
    def __init__(self, x):
        self.points = [(38, x), (800, x)]


class _Geometry:
    top = 38
    bottom = 800
    source_size = (1388, 2156)
    column_starts = (0, 708)
    column_widths = (671, 671)
    column_paths = (_Path(0), _Path(708))

    def x_at(self, index, _y):
        return self.column_starts[index]

    def canonical_to_source(self, x, y):
        return x, y


def _snapshot():
    return SimpleNamespace(
        geometry=_Geometry(), auto_enabled=True,
        method="reliable_fusion+long_explanation",
        confidence=.95, applied_fields={},
        raw_estimate={},
        used_values={
            "columns": 2, "start_y": 38, "bottom_y": 800,
            "manual_x": 0, "column_width": 671, "gutter": 37,
            "character_height": 31, "row_padding": 2,
        },
    )


def test_base_layout_minimal_mode_has_only_geometry_not_text_or_summary(monkeypatch):
    monkeypatch.setattr(base, "_snapshot_for_app", lambda _app: _snapshot())
    canvas = _Canvas()
    app = SimpleNamespace(
        canvas=canvas, image=object(), view_scale=.6,
        _layout_visualization_var=_Flag(True),
        hide_var=_Flag(False), crop_preview_var=_Flag(False),
        settings=SimpleNamespace(guide_color="#1976d2"),
    )
    base.draw_layout_visualization(app, minimal_text=True)
    assert canvas.lines
    assert canvas.text == []
    assert canvas.rectangles == []

    base.draw_layout_visualization(app, minimal_text=False)
    assert len(canvas.text) >= 5
    assert any(
        "Layout AUTO" in str(kwargs.get("text", ""))
        for _, kwargs in canvas.text
    )


def test_compact_layout_skips_legacy_yellow_indent_blocks_and_full_text(monkeypatch):
    monkeypatch.setattr(summary, "_snapshot_for_app", lambda _app: _snapshot())
    seen = []
    monkeypatch.setattr(
        summary, "draw_layout_visualization",
        lambda app, *, minimal_text=False: seen.append(("geometry", minimal_text)),
    )
    monkeypatch.setattr(
        summary, "_draw_role_strips",
        lambda app, snapshot: seen.append(("role_strips", snapshot.geometry.top)),
    )
    monkeypatch.setattr(
        summary, "_draw_indent_blocks",
        lambda app, snapshot: seen.append(("yellow_indents", True)),
    )
    summary.draw_layout_visualization_clean(SimpleNamespace(canvas=object()))
    assert seen == [("geometry", True), ("role_strips", 38)]


def test_normal_layout_toggle_uses_compact_and_candidate_view(monkeypatch):
    actions = []
    monkeypatch.setattr(
        summary, "draw_layout_visualization_clean",
        lambda app: actions.append("compact"),
    )
    monkeypatch.setattr(
        controls, "draw_layout_visualization_detailed",
        lambda app: actions.append("old_full"),
    )
    import picture_capture.ordinary_unified_visualization as vis
    monkeypatch.setattr(
        vis, "draw_unified_candidate_overlay",
        lambda app, *, layout_enabled: actions.append("candidate_overlay"),
    )
    app = SimpleNamespace(
        image=object(), _layout_visualization_var=_Flag(True),
        _layout_display_density_var=_Flag("简洁"),
        hide_var=_Flag(True),
    )
    controls.draw_layout_visualization_if_enabled(app)
    assert actions == ["compact", "candidate_overlay"]
    assert app.hide_var.get() is True

    actions.clear()
    app._layout_display_density_var.set("候选")
    controls.draw_layout_visualization_if_enabled(app)
    assert actions == ["compact", "candidate_overlay"]

    actions.clear()
    app._layout_display_density_var.set("详细")
    controls.draw_layout_visualization_if_enabled(app)
    assert actions == ["old_full", "candidate_overlay"]


def test_compact_only_conflicts_are_painted_and_candidate_mode_is_clickable(monkeypatch):
    import picture_capture.large_head_visualization_ui as ui

    rows = []
    for idx in range(100):
        bad = idx in (5, 38, 61)
        rows.append({
            "id": f"C01-R{idx+1:03d}",
            "column": 0, "source_anchor": [3, 50+idx*38],
            "physical_row": {"role": "entry"},
            "final_entries": [] if bad else [{"x": 3, "y": 50+idx*38}],
            "has_final_line": not bad,
            "issues": ["layout_entry_without_final_line"] if bad else [],
            "shadow_assessment": {
                "label": "review_conflict" if bad else "baseline_headword",
            },
        })
    registry = {"unified_report": {
        "registry": rows,
        "summary": {"candidates_total": 100, "final_lines": 97,
                    "review_items": 3},
    }}
    monkeypatch.setattr(ui, "get_large_head_debug_snapshot", lambda app: registry)
    canvas = _Canvas()
    app = SimpleNamespace(
        canvas=canvas, image=object(), view_scale=.5,
        _layout_display_density_var=_Flag("简洁"),
    )
    draw_unified_candidate_overlay(app, layout_enabled=True)
    assert len(canvas.rectangles) == 6  # marker + matching-ID badge
    assert canvas.text and len(canvas.text) == 6  # three ! + three ID labels
    assert not any(
        "统一Layout候选" in str(kwargs.get("text", ""))
        for _, kwargs in canvas.text
    )
    assert len(canvas.bindings) >= 3
    canvas.rectangles.clear()
    canvas.text.clear()
    canvas.bindings.clear()
    app._layout_display_density_var.set("候选")
    draw_unified_candidate_overlay(app, layout_enabled=True)
    assert len(canvas.rectangles) == 200  # square + ID background
    assert len(canvas.bindings) >= 200
    assert sum(str(kwargs.get("text", "")).startswith("C01-R")
               for _coords, kwargs in canvas.text) == 100
    assert not any(
        "统一Layout候选" in str(kwargs.get("text", ""))
        for _, kwargs in canvas.text
    )
