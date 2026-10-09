"""Phase 13D gate: explicit composed policy agrees with the installed chain."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from picture_capture import dictionary_page_design as base
from picture_capture import dictionary_page_layout_policy as policy
from picture_capture import layout_composition
from picture_capture import layout_line_start_refinement as robust
from picture_capture import layout_physical_indent as physical
from picture_capture.layout_profile_anchor import anchor_resolved_layout_to_profile
from picture_capture.models import AppSettings


def _scan():
    image = Image.new("RGB", (340, 220), "white")
    canvas = ImageDraw.Draw(image)
    for index, y in enumerate(range(16, 175, 22)):
        x = 20 if index % 3 == 0 else 30
        canvas.rectangle((x, y, x + 8, y + 12), fill="black")
        canvas.rectangle((62, y, 105, y + 12), fill="black")
    settings = AppSettings(
        columns=1, manual_x=16, column_width=180,
        start_y=7, character_height=14, ordinary_auto_layout=False,
    )
    return image, settings


def _layout_snapshot(result):
    layout, page_settings, applied = result
    columns = []
    for column in layout.columns:
        rows = [
            (line.y0, line.y1, line.first_x, line.anchor_x,
             line.role, line.has_small_prefix)
            for line in column.lines
        ]
        modes = sorted(
            (round(float(mode.center), 6), int(mode.support), mode.role)
            for mode in column.indent_modes
        )
        columns.append((column.left, column.right, rows, modes,
                        len(column.entry_modes)))
    return (layout.body_top, layout.body_bottom, layout.reliable,
            layout.reason, columns, applied,
            page_settings.column_width, page_settings.manual_x)


def test_composed_policy_matches_legacy_wrapped_policy(monkeypatch):
    image, settings = _scan()
    explicit = layout_composition.infer_composed_physical_page_layout(
        image, settings, page_index=0,
    )

    def legacy_policy(image, settings, *, page_index=0, ops=None):
        resolved, estimate, applied = policy._RAW_RESOLVE_PAGE_LAYOUT_POLICY(
            image, settings, page_index=page_index,
            **({"ops": ops} if ops is not None else {}),
        )
        anchored, selected = anchor_resolved_layout_to_profile(
            settings, resolved, applied,
        )
        return anchored, estimate, selected

    monkeypatch.setattr(policy, "resolve_page_layout_policy", legacy_policy)
    monkeypatch.setattr(base, "_line_runs", physical.projection_line_runs)
    monkeypatch.setattr(
        physical, "_BASE_LINE_FEATURE",
        robust.compose_robust_line_feature(base.RAW_LAYOUT_OPS.line_feature),
    )
    monkeypatch.setattr(base, "_line_feature", physical.physical_line_feature)
    monkeypatch.setattr(base, "_indent_modes", physical.physical_indent_modes)
    monkeypatch.setattr(base, "_assign_indent_semantics", physical.assign_binary_roles)
    installed = policy._RAW_INFER_DICTIONARY_PAGE_LAYOUT(
        image, settings, page_index=0,
    )
    physical.normalize_layout_roles(installed[0])
    assert _layout_snapshot(explicit) == _layout_snapshot(installed)


def test_unlined_composed_boundary_retains_physical_only_scope():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    source = (root / "unlined_physical_rows_resolver.py").read_text(encoding="utf-8")
    assert "infer_composed_physical_page_layout" in source
    assert "install_physical_indent_inference()" not in source
    assert "install_robust_line_starts()" not in source
    assert "understand_layout_core(" not in source
    assert "detect_ordinary_symbol_entries(" not in source
    assert "detect_ordinary_large_head_entries(" not in source
