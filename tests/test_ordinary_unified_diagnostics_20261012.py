"""One evidence registry powers both Layout overlays and exported JSON.

These tests freeze the behavior contract: the shadow assessor never modifies
production output or elevates automatic separators to human ground truth.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from picture_capture.ordinary_unified_diagnostics import (
    SCHEMA, compose_ordinary_evidence_report,
)
from picture_capture.ordinary_unified_visualization import (
    draw_unified_candidate_overlay, format_candidate_detail,
)
import picture_capture.large_head_visualization_ui as large_ui


def _row(number, y, role, *, column=0):
    return {
        "id": f"C{column+1:02d}-R{number:03d}",
        "column": column,
        "canonical_y0": y, "canonical_y1": y+28,
        "source_x": 20+column*400, "source_y": y,
        "role": role, "entry_source": "indent",
        "first_x": 3.0 if role == "entry" else 41.0,
        "corrected_first_x": 3.0 if role == "entry" else 41.0,
    }


def _layout():
    return {
        "ordinary_line_height": 30.0,
        "columns": [{"left": 20, "right": 390}],
        "physical_rows": [
            _row(1, 100, "entry"),
            _row(2, 141, "body"),
            _row(3, 205, "entry"),
            _row(4, 320, "entry"),
        ],
    }


def _entry(y, source="page_understanding:ordinary_layout_role"):
    return {
        "x": 20, "y": y,
        "source": source,
        "issue_type": "ORDINARY_LAYOUT_ROLE",
        "oversized": False,
    }


def _report():
    # Layout proposed three lines; the second was proven a body continuation,
    # and the third gained a verified bracket/large glyph source.
    stages = [
        {"stage": "layout_role_materialization",
         "entries": [_entry(100), _entry(141), _entry(205)]},
        {"stage": "bracketed_headword_recovery",
         "entries": [_entry(100, "ordinary_bracket_pair"), _entry(141),
                     _entry(205)]},
        {"stage": "proven_bracket_body_continuation",
         "entries": [_entry(100, "ordinary_bracket_pair"), _entry(205)]},
        {"stage": "final_reading_order",
         "entries": [_entry(100, "ordinary_bracket_pair"), _entry(205)]},
    ]
    glyphs = [{
        "status": "accepted", "source_box": (22, 205, 83, 278),
        "height_ratio": 2.4, "detector_output": True,
    }, {
        "status": "split_parent", "source_box": (20, 196, 170, 370),
        "recovered_count": 2,
    }]
    return compose_ordinary_evidence_report(
        _layout(), glyphs, stages, [], [
            _entry(100, "ordinary_bracket_pair"), _entry(205),
        ],
    )


def test_registry_has_stable_rows_evidence_stage_audit_and_shadow_only():
    report = _report()
    assert report["schema"] == SCHEMA
    assert report["policy"]["production_output_changed"] is False
    assert report["policy"]["ground_truth_available"] is False
    assert report["summary"]["physical_rows"] == 4
    assert report["summary"]["final_lines"] == 2

    row100 = next(row for row in report["registry"] if row["id"] == "C01-R001")
    assert row100["shadow_assessment"]["label"] == "supported_headword"
    assert any(e["type"] == "verified_bracket" for e in row100["evidence"])
    assert row100["stage_count"] == 4
    assert row100["has_final_line"]
    assert "ordinary_bracket_pair" in format_candidate_detail(row100)

    row141 = next(row for row in report["registry"] if row["id"] == "C01-R002")
    assert row141["shadow_assessment"]["label"] == "body"
    assert not row141["has_final_line"]
    assert row141["stage_trace"][-1]["stage"] == "bracketed_headword_recovery"
    assert row141["shadow_assessment"]["would_change_output"] is False

    row205 = next(row for row in report["registry"] if row["id"] == "C01-R003")
    assert any(e["type"] == "verified_large_head" for e in row205["evidence"])
    assert row205["detector_matches"][0]["status"] == "accepted"

    row320 = next(row for row in report["registry"] if row["id"] == "C01-R004")
    assert row320["issues"] == ["layout_entry_without_final_line"]
    assert any(e["candidate_id"] == "C01-R004" for e in report["review_queue"])
    json.dumps(report, ensure_ascii=False)


def test_unmatched_final_line_is_a_review_item_not_a_virtual_truth():
    report = compose_ordinary_evidence_report(
        _layout(), [], [], [], [_entry(550, "unproven")],
    )
    orphan = next(row for row in report["registry"] if row["id"].startswith("U"))
    assert orphan["issues"] == ["final_line_without_matched_physical_row"]
    assert orphan["shadow_assessment"]["label"] == "review_conflict"
    assert orphan["shadow_assessment"]["would_change_output"] is False


def test_nearby_y_refinement_is_same_physical_candidate():
    stages = [
        {"stage": "layout_role_materialization", "entries": [_entry(100)]},
        {"stage": "coherent_separator_y_refinement", "entries": [_entry(105)]},
        {"stage": "final_reading_order", "entries": [_entry(105)]},
    ]
    report = compose_ordinary_evidence_report(
        _layout(), [], stages, [], [_entry(105)],
    )
    candidate = next(row for row in report["registry"] if row["id"] == "C01-R001")
    assert [stage["y"] for stage in candidate["stage_trace"]] == [100, 105, 105]
    assert candidate["has_final_line"] is True


class _Canvas:
    def __init__(self):
        self.bound = []
        self.created = []

    def delete(self, *args):
        self.created.append(("delete", args))

    def create_rectangle(self, *args, **kwargs):
        self.created.append(("rectangle", args, kwargs))
        return len(self.created)

    def create_text(self, *args, **kwargs):
        self.created.append(("text", args, kwargs))
        return len(self.created)

    def tag_bind(self, index, event, callback):
        self.bound.append((index, event, callback))


def test_layout_ui_counts_are_exactly_the_exported_unified_json(monkeypatch):
    report = _report()
    snapshot = {"unified_report": report}
    monkeypatch.setattr(
        large_ui, "get_large_head_debug_snapshot", lambda app: snapshot,
    )
    # Imported lazily, patch its own function object once too.
    from picture_capture import ordinary_unified_visualization as vis
    canvas = _Canvas()
    app = SimpleNamespace(image=object(), canvas=canvas, view_scale=1)
    vis.draw_unified_candidate_overlay(app, layout_enabled=True)
    text = " ".join(item[2]["text"] for item in canvas.created
                    if item[0] == "text" and "text" in item[2])
    assert f"统一Layout候选 {report['summary']['candidates_total']}" in text
    assert f"最终线 {report['summary']['final_lines']}" in text
    assert f"待复核 {report['summary']['review_items']}" in text
    assert any(row[1] == "<Button-1>" for row in canvas.bound)
    before = json.dumps(report, ensure_ascii=False, sort_keys=True)
    vis.draw_unified_candidate_overlay(app, layout_enabled=False)
    assert json.dumps(report, ensure_ascii=False, sort_keys=True) == before


def test_appsettings_never_receives_shadow_decision_setting():
    from picture_capture.models import AppSettings
    settings = AppSettings()
    assert not hasattr(settings, "unified_ordinary_shadow_mode")
