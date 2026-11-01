"""R7.3 RED-first regressions for nonlinear polygon edges and source snapshots.

Synthetic geometry and EXIF metadata only. These tests do not modify any
persistent PDIC/PPP/SECTION/Profile/OCR data or image-processing defaults.
"""
from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from picture_capture.preprocess.coordinate_mapping import (
    CoordinateMappingUnavailable,
    PreprocessCoordinateMap,
)
from picture_capture.preprocess.models import PreprocessAnalysis


def _analysis(
    *,
    source_size: tuple[int, int] = (100, 101),
    crop_box: tuple[int, int, int, int] | None = None,
    separator_shift: tuple[float, float, float] | None = None,
) -> PreprocessAnalysis:
    width, height = source_size
    crop = crop_box or (0, 0, width, height)
    steps: tuple[dict[str, object], ...] = ()
    if separator_shift is not None:
        steps = ({
            "row_gain": 1.0,
            "reference_x": 0.0,
            "y_knots": [],
            "angle_knots_deg": [],
            "x_knots": [],
            "row_grid_rows": 0,
            "row_grid_cols": 0,
            "row_angle_grid_deg": [],
            "row_displacement_grid_px": [],
            "separator_y_knots": [0.0, 50.0, 100.0],
            "separator_shift_knots_px": list(separator_shift),
        },)
    return PreprocessAnalysis(
        source_width=width,
        source_height=height,
        correction_angle_deg=0.0,
        applied_angle_deg=0.0,
        crop_box=crop,
        raw_content_box=crop,
        text_box=crop,
        source_boxes=0,
        angle_samples=0,
        angle_mad_deg=0.0,
        retained_ratio=1.0,
        confidence=1.0,
        status="synthetic",
        method="r7_3_nonlinear_orthogonal_edge_regression",
        geometry_mode="perspective",
        perspective_matrix=None,
        orthogonal_applied=bool(steps),
        orthogonal_steps=steps,
    )


def test_source_polygon_edge_cannot_leave_half_open_crop_between_mapped_vertices():
    """A nonlinear separator shift can push an edge onto the excluded crop edge."""
    analysis = _analysis(
        source_size=(50, 101),
        crop_box=(0, 0, 50, 101),
        separator_shift=(0.0, -10.0, 0.0),
    )
    mapping = PreprocessCoordinateMap(analysis)
    polygon = ((40.0, 10.0), (45.0, 10.0),
               (45.0, 90.0), (40.0, 90.0))

    # Every vertex is individually valid. At y=50, however, the left edge
    # maps to x=50, exactly the right/bottom-exclusive crop boundary.
    assert all(mapping.source_to_output_point(point).status == "mapped"
               for point in polygon)
    assert mapping.source_to_output_polygon(polygon) is None


def test_output_polygon_inverse_edge_cannot_leave_source_between_mapped_vertices():
    """The inverse nonlinear mesh must be checked along edges, not only vertices."""
    analysis = _analysis(
        source_size=(50, 101),
        crop_box=(0, 0, 50, 101),
        separator_shift=(0.0, 10.0, 0.0),
    )
    mapping = PreprocessCoordinateMap(analysis)
    polygon = ((40.0, 10.0), (45.0, 10.0),
               (45.0, 90.0), (40.0, 90.0))

    # The output vertices are inside the crop and inverse-map inside the
    # source. Along the left edge, y=50 maps back to source x=50, outside
    # the valid [0, 50) source pixel domain.
    assert all(mapping.output_to_source_point(point).status == "mapped"
               for point in polygon)
    assert mapping.output_to_source_polygon(polygon) is None


@pytest.mark.parametrize(
    ("orientation", "oriented_size"),
    (
        (1, (40, 20)),
        (2, (40, 20)),
        (3, (40, 20)),
        (4, (40, 20)),
        (5, (20, 40)),
        (6, (20, 40)),
        (7, (20, 40)),
        (8, (20, 40)),
    ),
)
def test_source_size_snapshot_must_match_raw_size_and_exif_orientation(
    orientation, oriented_size,
):
    """The map's source frame is the EXIF-oriented pixel frame."""
    analysis = _analysis(
        source_size=oriented_size,
        crop_box=(0, 0, oriented_size[0], oriented_size[1]),
    )
    mapping = PreprocessCoordinateMap(
        analysis,
        source_size=oriented_size,
        raw_source_size=(40, 20),
        exif_orientation=orientation,
    )
    assert mapping.source_size == oriented_size
    assert mapping.raw_source_size == (40, 20)
    assert mapping.exif_orientation == orientation


def test_source_size_snapshot_matches_pillow_exif_transpose_dimensions():
    from picture_capture.preprocess.page_pixels import normalize_page_rgb

    original = Image.new("RGB", (40, 20), "white")
    exif = original.getexif()
    exif[274] = 6
    stream = BytesIO()
    original.save(stream, format="JPEG", exif=exif)
    original.close()
    stream.seek(0)

    with Image.open(stream) as decoded:
        raw_size = decoded.size
        orientation = int(decoded.getexif().get(274, 1))
        oriented = normalize_page_rgb(decoded)
    try:
        assert raw_size == (40, 20)
        assert orientation == 6
        assert oriented.size == (20, 40)
        analysis = _analysis(
            source_size=oriented.size,
            crop_box=(0, 0, oriented.width, oriented.height),
        )
        mapping = PreprocessCoordinateMap(
            analysis,
            source_size=oriented.size,
            raw_source_size=raw_size,
            exif_orientation=orientation,
        )
        assert mapping.source_size == oriented.size
    finally:
        oriented.close()


def test_exif_orientation_dimension_mismatch_fails_closed():
    analysis = _analysis(source_size=(40, 20))
    with pytest.raises(ValueError, match="EXIF"):
        PreprocessCoordinateMap(
            analysis,
            source_size=(40, 20),
            raw_source_size=(40, 20),
            exif_orientation=6,
        )


@pytest.mark.parametrize("source_size", ((), (100.5, 100)))
def test_source_size_rejects_empty_or_fractional_dimensions(source_size):
    with pytest.raises(ValueError, match="source_size"):
        PreprocessCoordinateMap(
            _analysis(source_size=(100, 101)),
            source_size=source_size,
        )


def test_malformed_legacy_orthogonal_snapshot_is_normalized_to_unavailable():
    analysis = _analysis(separator_shift=None)
    analysis.orthogonal_applied = True
    analysis.orthogonal_y_knots = (0.0, None, 100.0)
    analysis.orthogonal_angle_knots_deg = (0.0, 0.0, 0.0)

    with pytest.raises(CoordinateMappingUnavailable, match="orthogonal"):
        PreprocessCoordinateMap(analysis)


def test_malformed_orthogonal_row_grid_decoder_fails_closed():
    analysis = _analysis(
        separator_shift=(0.0, 1.0, 0.0),
    )
    payload = dict(analysis.orthogonal_steps[0])
    payload["row_grid_rows"] = float("inf")
    analysis.orthogonal_steps = (payload,)

    with pytest.raises(CoordinateMappingUnavailable, match="orthogonal"):
        PreprocessCoordinateMap(analysis)
