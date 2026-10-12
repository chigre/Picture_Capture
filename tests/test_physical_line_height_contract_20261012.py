"""Physical projection must not lose valid ink rows in the layout consumer."""
import numpy as np
from PIL import Image

from picture_capture import dictionary_page_design as design
from picture_capture.models import AppSettings


def test_physical_projection_keeps_real_30px_rows_with_18px_nominal_height(monkeypatch):
    # Actual XDHYCD right column: most visible 29-32px ink bands were lost
    # because projection accepts <=1.90h while PageDesign kept only <=1.55h.
    monkeypatch.setattr(design, "_normal_height", lambda runs, seed: 18.0)

    def physical_rows(ink, scale):
        return [(35, 65), (90, 120), (150, 180)]

    physical_rows.__name__ = "projection_line_runs"

    def row_feature(column, ink, y0, y1, reference, previous_end):
        return design.LayoutLine(
            column, y0, y1, 10, None, 0, 0,
            max(0, y0 - previous_end), np.zeros((0, 0), dtype=bool),
        )

    ops = design.LayoutPrimitiveOps(
        line_runs=physical_rows,
        line_feature=row_feature,
        indent_modes=lambda lines, ref: [],
        assign_indent_semantics=lambda column, indent, ref: None,
    )
    settings = AppSettings(
        columns=2, column_width=250, gutter=20, manual_x=20,
        character_height=18, start_y=20, ordinary_auto_layout=False,
    )
    blank = Image.new("L", (580, 280), 255)
    from PIL import ImageDraw
    draw = ImageDraw.Draw(blank)
    for x in (35, 310):
        for y in (55, 110, 170):
            draw.rectangle((x, y, x + 165, y + 25), fill=0)
    output = design.infer_dictionary_page_layout(blank, settings, ops=ops)
    assert len(output.columns) == 2
    assert all(len(column.lines) == 3 for column in output.columns)
    assert all(line.height == 30 for column in output.columns for line in column.lines)

    # Legacy nonprojection runners keep their own stricter contract.
    physical_rows.__name__ = "legacy_rows"
    old = design.infer_dictionary_page_layout(blank, settings, ops=ops)
    assert all(len(column.lines) == 0 for column in old.columns)


def test_per_page_policy_does_not_drop_30px_physical_rows(monkeypatch):
    """The policy consumer must match the lower-level PageDesign contract."""
    from picture_capture import dictionary_page_layout_policy as policy

    monkeypatch.setattr(design, "_normal_height", lambda _runs, _seed: 18.0)

    def physical_rows(_ink, _scale):
        return [(35, 65), (90, 120), (150, 180)]

    physical_rows.__name__ = "projection_line_runs"

    def row_feature(index, _strip, y0, y1, _ref, _prev):
        return design.LayoutLine(
            index, y0, y1, 10, None, 0, 0, 0,
            np.zeros((0, 0), dtype=bool),
        )

    ops = design.LayoutPrimitiveOps(
        line_runs=physical_rows, line_feature=row_feature,
        indent_modes=lambda _lines, _ref: [],
        assign_indent_semantics=lambda _column, _indent, _ref: None,
    )
    settings = AppSettings(
        columns=2, column_width=250, gutter=20, manual_x=20,
        character_height=18, start_y=20, ordinary_auto_layout=False,
        profile_header_mode="none", profile_footer_mode="none",
        profile_side_content_mode="none",
    )
    img = Image.new("L", (580, 280), 255)
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    for x in (35, 310):
        for y in (55, 110, 170):
            draw.rectangle((x, y, x+165, y+25), fill=0)
    layout, _settings, _applied = policy.infer_dictionary_page_layout(
        img, settings, ops=ops,
    )
    assert all(len(col.lines) == 3 for col in layout.columns)
    assert all(line.height == 30 for col in layout.columns for line in col.lines)
