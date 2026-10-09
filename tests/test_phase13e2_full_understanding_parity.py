"""Phase 13E: compare full Page Understanding under installed and explicit chains."""
from PIL import Image, ImageDraw

from picture_capture import dictionary_page_design as base
from picture_capture import dictionary_page_layout_policy as policy
from picture_capture import layout_composition
from picture_capture import layout_line_start_refinement as robust
from picture_capture import layout_physical_indent as physical
from picture_capture import page_understanding as page
from picture_capture.layout_profile_anchor import anchor_resolved_layout_to_profile
from picture_capture.models import AppSettings


def _page():
    image = Image.new("RGB", (340, 225), "white")
    draw = ImageDraw.Draw(image)
    for i in range(8):
        y = 16 + i * 23
        x = 20 if i % 4 == 0 else 30
        draw.rectangle((x, y, x + 8, y + 12), fill="black")
        draw.rectangle((64, y, 112, y + 12), fill="black")
    settings = AppSettings(
        columns=1, manual_x=16, column_width=190,
        start_y=6, character_height=14, ordinary_auto_layout=False,
    )
    return image, settings


def _snapshot(result):
    layout = result.layout
    columns = []
    for col in layout.columns:
        columns.append((
            col.left, col.right,
            [(line.y0, line.y1, line.first_x, line.anchor_x, line.role)
             for line in col.lines],
            [(round(float(mode.center), 5), mode.role, mode.support)
             for mode in col.indent_modes],
            len(col.entry_modes),
        ))
    return (
        result.role_model, result.physical_reliable, result.semantic_reliable,
        result.family_offset_ratio, result.generic_body_indent_reliable,
        result.page_settings.manual_x, result.applied_layout_fields,
        [(entry.x, entry.y) for entry in result.semantic_entries],
        len(result.symbol_evidence.markers),
        layout.reason, columns,
    )


def test_composed_full_understanding_parity_with_installed_chain(monkeypatch):
    image, settings = _page()
    explicit = layout_composition.understand_composed_page(image, settings)

    def legacy_resolve(source, original_settings, *, page_index=0, ops=None):
        resolved, estimate, applied = policy._RAW_RESOLVE_PAGE_LAYOUT_POLICY(
            source, original_settings, page_index=page_index,
            **({"ops": ops} if ops is not None else {}),
        )
        anchored, applied = anchor_resolved_layout_to_profile(
            original_settings, resolved, applied,
        )
        return anchored, estimate, applied

    monkeypatch.setattr(base, "_line_runs", physical.projection_line_runs)
    monkeypatch.setattr(
        physical, "_BASE_LINE_FEATURE",
        robust.compose_robust_line_feature(base.RAW_LAYOUT_OPS.line_feature),
    )
    monkeypatch.setattr(base, "_line_feature", physical.physical_line_feature)
    monkeypatch.setattr(base, "_indent_modes", physical.physical_indent_modes)
    monkeypatch.setattr(base, "_assign_indent_semantics", physical.assign_binary_roles)

    def legacy_infer(source, options, *, page_index=0):
        layout, resolved, applied = policy._RAW_INFER_DICTIONARY_PAGE_LAYOUT(
            source, options, page_index=page_index,
            policy_resolver=legacy_resolve,
        )
        physical.normalize_layout_roles(layout)
        return layout, resolved, applied

    monkeypatch.setattr(page, "infer_dictionary_page_layout", legacy_infer)
    installed = page._RAW_UNDERSTAND_PAGE(image, settings)
    physical.normalize_layout_roles(installed.layout)
    assert _snapshot(explicit) == _snapshot(installed)
