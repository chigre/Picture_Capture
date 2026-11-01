"""R7.3 RED-first regressions for nonlinear polygon edges and source snapshots.

Synthetic geometry and EXIF metadata only. These tests do not modify any
persistent PDIC/PPP/SECTION/Profile/OCR data or image-processing defaults.
"""
from __future__ import annotations

from io import BytesIO

import numpy as np
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
    separator_shift: tuple[float, ...] | None = None,
    separator_y_knots: tuple[float, ...] = (0.0, 50.0, 100.0),
    perspective_matrix: tuple[float, ...] | None = None,
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
            "separator_y_knots": list(separator_y_knots),
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
        perspective_matrix=perspective_matrix,
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



def test_source_polygon_checks_narrow_excursion_at_exact_orthogonal_knot():
    """A sub-8px separator excursion must not hide between uniform samples."""
    analysis = _analysis(
        source_size=(50, 101),
        crop_box=(0, 0, 50, 101),
        separator_shift=(0.0, 0.0, -10.0, 0.0, 0.0),
        separator_y_knots=(0.0, 52.0, 53.0, 54.0, 100.0),
    )
    mapping = PreprocessCoordinateMap(analysis)
    polygon = ((40.0, 10.0), (45.0, 10.0),
               (45.0, 90.0), (40.0, 90.0))

    assert all(mapping.source_to_output_point(point).status == "mapped"
               for point in polygon)
    assert mapping.source_to_output_polygon(polygon) is None


def test_inverse_polygon_checks_narrow_excursion_at_exact_orthogonal_knot():
    """Inverse ROI edges must sample the saved field's exact knot locations."""
    analysis = _analysis(
        source_size=(50, 101),
        crop_box=(0, 0, 50, 101),
        separator_shift=(0.0, 0.0, 10.0, 0.0, 0.0),
        separator_y_knots=(0.0, 52.0, 53.0, 54.0, 100.0),
    )
    mapping = PreprocessCoordinateMap(analysis)
    polygon = ((40.0, 10.0), (45.0, 10.0),
               (45.0, 90.0), (40.0, 90.0))

    assert all(mapping.output_to_source_point(point).status == "mapped"
               for point in polygon)
    assert mapping.output_to_source_polygon(polygon) is None


def test_polygon_mapping_accepts_numpy_point_arrays():
    """The Sequence API also accepts NumPy arrays without truth-value ambiguity."""
    analysis = _analysis(
        source_size=(100, 101),
        crop_box=(0, 0, 100, 101),
        separator_shift=None,
    )
    mapping = PreprocessCoordinateMap(analysis)
    polygon = np.asarray(
        ((20.0, 20.0), (60.0, 20.0), (60.0, 60.0), (20.0, 60.0)),
        dtype=float,
    )

    output = mapping.source_to_output_polygon(polygon)
    assert output is not None and len(output) == 4
    restored = mapping.output_to_source_polygon(np.asarray(output, dtype=float))
    assert restored is not None
    assert np.allclose(restored, polygon, atol=0.02)
    assert mapping.source_to_output_polygon(np.empty((0, 2))) is None
    assert mapping.output_to_source_polygon(np.empty((0, 2))) is None



def test_source_polygon_samples_separator_knots_after_projective_transform():
    """Knot crossings belong to the orthogonal input frame, not raw source XY."""
    analysis = _analysis(
        source_size=(50, 101),
        crop_box=(0, 0, 50, 101),
        separator_shift=(0.0, 0.0, -10.0, 0.0, 0.0),
        separator_y_knots=(0.0, 52.0, 53.0, 54.0, 100.0),
        perspective_matrix=(
            1.0, 0.0, 0.0,
            0.0, 1.0, 20.0,
            0.0, 0.0, 1.0,
        ),
    )
    mapping = PreprocessCoordinateMap(analysis)
    polygon = ((38.0, 10.0), (40.0, 10.0),
               (40.0, 70.0), (38.0, 70.0))

    assert all(mapping.source_to_output_point(point).status == "mapped"
               for point in polygon)
    # The source edge at y=33 becomes orthogonal-input y=53 after H.
    assert mapping.source_to_output_point((40.0, 33.0)).status == "outside_crop"
    assert mapping.source_to_output_polygon(polygon) is None


def test_inverse_polygon_samples_separator_knots_after_crop_and_canvas_offsets():
    """Reverse knot crossings must undo both canvas and crop offsets first."""
    from picture_capture.preprocess.canvas import output_canvas_info

    analysis = _analysis(
        source_size=(50, 101),
        crop_box=(0, 20, 50, 101),
        separator_shift=(0.0, 0.0, 10.0, 0.0, 0.0),
        separator_y_knots=(0.0, 52.0, 53.0, 54.0, 100.0),
    )
    canvas = output_canvas_info(
        analysis,
        enabled=True,
        mode="custom",
        requested_width=70,
        requested_height=111,
        canvas_width=70,
        canvas_height=111,
        margin_top=15,
        margin_bottom=15,
        margin_left=10,
        margin_right=10,
        align_x="center",
        align_y="center",
    )
    mapping = PreprocessCoordinateMap(analysis, canvas=canvas)
    polygon = ((45.0, 25.0), (50.0, 25.0),
               (50.0, 85.0), (45.0, 85.0))

    assert all(mapping.output_to_source_point(point).status == "mapped"
               for point in polygon)
    # Output (50, 48) -> canvas-relative (40, 33) -> pre-crop (40, 53).
    # Inverse separator shift sends source X exactly to the excluded boundary 50.
    assert mapping.output_to_source_point((50.0, 48.0)).status == "outside_source"
    assert mapping.output_to_source_polygon(polygon) is None


@pytest.mark.parametrize(
    "crop_box",
    (
        (0.5, 0, 50, 101),
        (0, 0, 50.5, 101),
        (False, 0, 50, 101),
    ),
)
def test_crop_box_rejects_fractional_or_boolean_half_open_coordinates(crop_box):
    """Half-open raster boxes must not be silently truncated by int()."""
    analysis = _analysis(
        source_size=(50, 101),
        crop_box=(0, 0, 50, 101),
        separator_shift=None,
    )
    analysis.crop_box = crop_box

    with pytest.raises(ValueError, match="crop_box"):
        PreprocessCoordinateMap(analysis)
