"""R7.3 cross-owner contract: projected views never rewrite persisted source XY.

Synthetic image/PDIC/PPP/SECTION fixtures only. No production data or writer
semantics are changed by constructing and using PreprocessCoordinateMap.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from picture_capture.geometry.layout_transform import LayoutTransform
from picture_capture.io.formats import read_pdic, read_ppp, write_pdic, write_ppp
from picture_capture.models import Entry, PolygonRegion
from picture_capture.persistence.page_sections import PageSection, write_page_sections
from picture_capture.preprocess.canvas import output_canvas_info
from picture_capture.preprocess.coordinate_mapping import PreprocessCoordinateMap
from picture_capture.preprocess.models import PreprocessAnalysis
from picture_capture.preprocess.pipeline import geometry_corrected_image
from picture_capture.preprocess.rendering import (
    processed_image,
    processed_image_with_canvas,
)
from picture_capture.proofreading.review_section_provenance import (
    section_key_for_source_point,
)


@pytest.mark.parametrize(
    "kind", ("identity", "mirror_x", "rotate_ccw90", "rotate_cw90"),
)
def test_pdic_ppp_section_source_xy_survives_canonical_crop_canvas_projection(
    tmp_path, kind,
):
    """One source marker/polygon survives every canonical orientation unchanged."""
    page = tmp_path / "001.png"
    source = Image.new("RGB", (101, 81), "white")
    ImageDraw.Draw(source).rectangle((30, 35, 33, 38), fill="black")
    source.save(page)

    source_point = (31, 36)
    source_polygon = ((30, 35), (33, 35), (33, 38), (30, 38))
    transform = LayoutTransform(kind)
    canonical = transform.canonical_image_for_analysis(source)
    width, height = canonical.size

    orthogonal_steps = tuple(
        {
            "row_gain": 1.0,
            "reference_x": 0.0,
            "y_knots": [0.0, float(height - 1)],
            "angle_knots_deg": [0.0, 0.0],
            "x_knots": [],
            "row_grid_rows": 0,
            "row_grid_cols": 0,
            "row_angle_grid_deg": [],
            "row_displacement_grid_px": [],
            "separator_y_knots": [0.0, float(height - 1)],
            "separator_shift_knots_px": [shift, shift],
        }
        for shift in (2.0, 1.0)
    )
    analysis = PreprocessAnalysis(
        source_width=width,
        source_height=height,
        correction_angle_deg=0.0,
        applied_angle_deg=0.0,
        crop_box=(8, 9, width - 8, height - 9),
        raw_content_box=(8, 9, width - 8, height - 9),
        text_box=(8, 9, width - 8, height - 9),
        source_boxes=0,
        angle_samples=0,
        angle_mad_deg=0.0,
        retained_ratio=0.75,
        confidence=1.0,
        status="synthetic",
        method="r7_3_source_annotation_projection",
        geometry_mode="perspective",
        perspective_matrix=(
            1.0, 0.0, 3.0,
            0.0, 1.0, 4.0,
            0.0, 0.0, 1.0,
        ),
        orthogonal_applied=True,
        orthogonal_steps=orthogonal_steps,
    )
    crop_width = analysis.crop_box[2] - analysis.crop_box[0]
    crop_height = analysis.crop_box[3] - analysis.crop_box[1]
    canvas = output_canvas_info(
        analysis,
        enabled=True,
        mode="custom",
        requested_width=crop_width + 32,
        requested_height=crop_height + 28,
        canvas_width=crop_width + 32,
        canvas_height=crop_height + 28,
        margin_top=3,
        margin_bottom=5,
        margin_left=5,
        margin_right=7,
        align_x="center",
        align_y="center",
    )

    pdic = page.with_suffix(".PDIC")
    ppp = page.with_suffix(".ppp")
    write_pdic(pdic, [Entry("marker", *source_point)], source.width, ("001", "@", "@"))
    write_ppp(
        ppp,
        [PolygonRegion("manual-region", list(source_polygon))],
        page.stem,
    )
    canonical_v = transform.source_to_canonical_point(
        *source_point, source.size,
    )[1]
    section = write_page_sections(
        page,
        [PageSection(canonical_v - 5, canonical_v + 6)],
        layout_transform=kind,
    )

    # Persisted PDIC, PPP and SECTION are the source-coordinate record. A
    # transformed preview is an ephemeral projection and must not rewrite it.
    before = {
        path: path.read_bytes()
        for path in (page, pdic, ppp, section)
    }
    assert [(row.x, row.y) for row in read_pdic(pdic)] == [source_point]
    assert read_ppp(ppp)[0].points == list(source_polygon)
    assert section_key_for_source_point(page, section, *source_point) == "section-1"

    mapping = PreprocessCoordinateMap(
        analysis=analysis,
        source_size=source.size,
        layout_transform=transform,
        canvas=canvas,
        analysis_is_canonicalized=(kind != "identity"),
    )
    mapped = mapping.source_to_output_point(source_point)
    assert mapped.status == "mapped"
    assert mapped.point is not None
    assert mapped.approximate is True
    restored = mapping.output_to_source_point(mapped.point)
    assert restored.status == "mapped"
    assert restored.point == pytest.approx(source_point, abs=1e-9)

    mapped_polygon = mapping.source_to_output_polygon(source_polygon)
    assert mapped_polygon is not None and len(mapped_polygon) == 4
    restored_polygon = mapping.output_to_source_polygon(mapped_polygon)
    assert restored_polygon is not None
    assert np.allclose(restored_polygon, source_polygon, atol=1e-9)

    rendered = processed_image_with_canvas(
        canonical,
        analysis,
        canvas,
        content_renderer=lambda image, item: processed_image(
            image, item, geometry_renderer=geometry_corrected_image,
        ),
        canvas_info_factory=output_canvas_info,
    )
    pixel = tuple(int(round(value)) for value in mapped.point)
    assert rendered.getpixel(pixel) == (0, 0, 0)

    # Padding and the right/bottom half-open content boundary are not source
    # pixels and must never acquire a guessed source annotation coordinate.
    assert mapping.output_to_source_point((0.0, 0.0)).status == "outside_crop"
    assert mapping.output_to_source_point(
        (float(canvas.content_box[2]), float(canvas.content_box[3] - 1)),
    ).status == "outside_crop"
    assert mapping.source_to_output_point((0.0, 0.0)).status == "outside_crop"

    assert {
        path: path.read_bytes()
        for path in (page, pdic, ppp, section)
    } == before
