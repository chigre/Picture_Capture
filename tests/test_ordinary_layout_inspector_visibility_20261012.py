"""Ensure Layout inspection is discoverable and visible rather than 6px/off-page.

No production ordinary detection or saved PDIC is modified.
"""
from __future__ import annotations

from types import SimpleNamespace

from picture_capture.ordinary_layout_inspector import (
    _FILTERS, _filtered_registry, _row_values, focus_layout_candidate,
)
from picture_capture.ordinary_unified_visualization import (
    draw_unified_candidate_overlay,
)


class _Canvas:
    def __init__(self):
        self.rectangles = []
        self.texts = []
        self.bound = []
        self.deleted = []
        self.views = []

    def delete(self, *args):
        self.deleted.append(args)

    def create_rectangle(self, *args, **kwargs):
        self.rectangles.append((args, kwargs))
        return len(self.rectangles)

    def create_text(self, *args, **kwargs):
        self.texts.append((args, kwargs))
        return len(self.texts)

    def tag_bind(self, ident, binding, handler):
        self.bound.append((ident, binding, handler))

    def tag_raise(self, tag):
        return None

    def winfo_height(self):
        return 400

    def winfo_width(self):
        return 400

    def yview_moveto(self, location):
        self.views.append(("y", location))

    def xview_moveto(self, location):
        self.views.append(("x", location))


def _row(identifier, y, *, conflict=False, final=True, role="entry"):
    return {
        "id": identifier,
        "column": 0,
        "source_anchor": [3, y],
        "physical_row": {"role": role},
        "evidence": [{"type": "layout_entry", "origin": "physical",
                      "strength": "moderate"}],
        "issues": (["layout_entry_without_final_line"] if conflict else []),
        "shadow_assessment": {
            "label": "review_conflict" if conflict else "baseline_headword",
        },
        "final_entries": ([{"x": 3, "y": y}] if final else []),
        "has_final_line": final,
        "detector_matches": [],
        "stage_trace": [],
    }


def test_layout_inspector_filters_and_summary_share_identical_registry():
    a = _row("C01-R001", 100)
    b = _row("C01-R002", 500, conflict=True, final=False)
    c = _row("C01-R003", 800, role="body", final=False)
    c["detector_matches"] = [{"status": "rejected_row_front"}]
    registry = [a, b, c]
    assert [r["id"] for r in _filtered_registry(registry, _FILTERS[0])] == [
        "C01-R002",
    ]
    assert len(_filtered_registry(registry, _FILTERS[1])) == 3
    assert [r["id"] for r in _filtered_registry(registry, _FILTERS[2])] == [
        "C01-R001",
    ]
    assert len(_filtered_registry(registry, _FILTERS[3])) == 2
    assert [r["id"] for r in _filtered_registry(registry, _FILTERS[4])] == [
        "C01-R003",
    ]
    assert _row_values(a)[0] == "C01-R001"
    assert "Layout 判 entry" in _row_values(b)[-1]


def test_annotated_markers_are_visible_and_clickable_at_reduced_zoom(monkeypatch):
    import picture_capture.large_head_visualization_ui as ui

    rows = [
        _row("C01-R001", 100),
        _row("C01-R002", 500, conflict=True, final=False),
    ]
    report = {
        "registry": rows,
        "summary": {"candidates_total": 2, "final_lines": 1,
                    "review_items": 1},
    }
    monkeypatch.setattr(
        ui, "get_large_head_debug_snapshot",
        lambda app: {"unified_report": report},
    )

    canvas = _Canvas()
    app = SimpleNamespace(canvas=canvas, image=object(), view_scale=.27)
    draw_unified_candidate_overlay(app, layout_enabled=True)

    # Even when column1 starts at x=3 and zoom is .27, neither icon is clipped
    # at negative x nor reduced to a non-clickable 1.6px mark.
    # One square + one matching-ID background for each candidate.
    assert len(canvas.rectangles) == 4
    for coords, kwargs in canvas.rectangles:
        x0, y0, x1, y1 = coords
        assert x0 >= 0
        assert x1-x0 >= 16
        assert y1-y0 >= 16
        assert kwargs.get("tags")
    assert canvas.rectangles[2][1]["outline"] == "#d97706"
    ids = [props.get("text") for _pos, props in canvas.texts]
    assert "C01-R001" in ids and "C01-R002" in ids
    assert len(canvas.bound) >= 2
    summary = " ".join(k["text"] for _a, k in canvas.texts)
    # Full counters now live only in the off-image inspector and JSON.
    assert "统一Layout候选" not in summary
    assert "C01-R001" in summary and "C01-R002" in summary
    assert report["summary"]["review_items"] == 1


def test_markers_open_same_candidate_id_in_inspector(monkeypatch):
    import picture_capture.large_head_visualization_ui as ui
    import picture_capture.ordinary_layout_inspector as inspector

    row = _row("C01-R020", 840, conflict=True)
    monkeypatch.setattr(
        ui, "get_large_head_debug_snapshot",
        lambda app: {"unified_report": {
            "registry": [row],
            "summary": {"candidates_total": 1, "final_lines": 1,
                        "review_items": 1},
        }},
    )
    opened = []
    monkeypatch.setattr(
        inspector, "show_unified_layout_inspector",
        lambda app, *, candidate_id=None: opened.append(candidate_id),
    )
    canvas = _Canvas()
    app = SimpleNamespace(canvas=canvas, image=object(), view_scale=.5)
    draw_unified_candidate_overlay(app, layout_enabled=True)
    assert canvas.bound[0][2](None) == "break"
    assert canvas.bound[-1][2](None) == "break"
    # Both the green/orange square AND its background-ID text carry the same
    # exact candidate ID used as the Treeview row key.
    assert opened == ["C01-R020", "C01-R020"]
    badges = [x for x in canvas.texts
              if x[1].get("text") == "C01-R020"]
    assert len(badges) == 1
    marker = canvas.rectangles[0][0]
    background = canvas.rectangles[1][0]
    assert background[0] > marker[2]


def test_double_click_focus_scrolls_image_and_highlights_correct_source_position():
    canvas = _Canvas()
    app = SimpleNamespace(
        canvas=canvas, image=SimpleNamespace(width=1388, height=2156),
        view_scale=.5,
    )
    row = _row("C01-R025", 1800)
    assert focus_layout_candidate(app, row)
    assert canvas.rectangles
    assert "ordinary-layout-inspector-highlight" in (
        canvas.rectangles[-1][1]["tags"]
    )
    assert [kind for kind, _loc in canvas.views] == ["y", "x"]
    assert 0 <= canvas.views[0][1] <= 1
    assert canvas.views[0][1] > 0


def test_actual_compact_palette_contains_inspector_button():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src/picture_capture/ui/compact_display_menu.py"
    ).read_text(encoding="utf-8")
    assert 'text="查看Layout候选/异常", command=open_layout_inspector' in source
    overlay = (
        root / "src/picture_capture/layout_visualization_ui_v3.py"
    ).read_text(encoding="utf-8")
    assert "draw_unified_candidate_overlay(app, layout_enabled=True)" in overlay
    assert "add_unified_layout_inspector_controls(app, section)" in overlay


def test_real_inspector_window_renders_table_when_tk_is_available(monkeypatch):
    """Integration check: an actual Treeview is visible in a real Toplevel."""
    import tkinter as tk
    from tkinter import ttk
    import pytest

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no graphical Tk display in this pytest runner")
    root.withdraw()
    try:
        import picture_capture.large_head_visualization_ui as ui
        from picture_capture.ordinary_layout_inspector import (
            show_unified_layout_inspector,
        )

        rows = [
            _row("C01-R001", 100),
            _row("C01-R002", 500, conflict=True, final=False),
        ]
        monkeypatch.setattr(
            ui, "get_large_head_debug_snapshot",
            lambda _app: {"unified_report": {
                "registry": rows,
                "review_queue": [{
                    "candidate_id": "C01-R002",
                    "codes": ["layout_entry_without_final_line"],
                }],
                "summary": {"physical_rows": 2, "candidates_total": 2,
                            "final_lines": 1, "review_items": 1},
            }},
        )
        canvas = _Canvas()
        app = SimpleNamespace(
            canvas=canvas, image=SimpleNamespace(width=1388, height=2156),
            view_scale=1, root=root, current_index=8,
        )
        show_unified_layout_inspector(app, candidate_id="C01-R002")
        root.update_idletasks()
        window = app._ordinary_layout_inspector_window
        assert window.winfo_exists()
        assert "第9页" in window.title()

        def descend(widget):
            found = []
            for child in widget.winfo_children():
                found.append(child)
                found.extend(descend(child))
            return found

        tables = [
            widget for widget in descend(window)
            if isinstance(widget, ttk.Treeview)
        ]
        assert len(tables) == 1
        assert tables[0].get_children() == ("C01-R002",)
        assert tables[0].selection() == ("C01-R002",)
        window.destroy()
    finally:
        root.destroy()
