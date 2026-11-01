"""Read-only, versioned mapping between source, canonical and preprocess frames.

The map never edits images or persisted annotation data. It is available only
when every geometric stage has a supported point mapping; UVDoc deliberately
fails closed because its nonlinear deformation currently has no point-map
contract. Orthogonal inverse mapping follows the same bounded fixed-point
solver as the image mesh and is therefore marked approximate.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import math
from operator import index as integer_index
from typing import Literal, Sequence

import numpy as np

from ..geometry.layout_transform import LayoutTransform
from .deskew import _rotate_point_same_canvas
from .models import OutputCanvasInfo, PreprocessAnalysis
from .orthogonal_dewarp import (
    OrthogonalWarpEstimate,
    inverse_transform_points_orthogonal,
    transform_points_orthogonal,
)
from .orthogonal_policy import _orthogonal_estimate_from_step

COORDINATE_MAPPING_CONTRACT_VERSION = 1

# Orthogonal replay is nonlinear. Check each polygon edge at a bounded spatial
# interval no larger than one fifth of the default 40 px raster mesh cell,
# adding saved grid/separator knot crossings explicitly. This is a conservative
# boundary check, not a claim of sub-pixel exactness.
_ORTHOGONAL_POLYGON_SAMPLE_SPACING_PX = 8.0
_ORTHOGONAL_POLYGON_MAX_EDGE_STEPS = 8192
_ORTHOGONAL_POLYGON_MAX_TOTAL_SAMPLES = 32768


def _validated_size_pair(value: Sequence[int], name: str) -> tuple[int, int]:
    """Return a strict positive integer (width, height) snapshot."""
    try:
        if isinstance(value, (str, bytes)) or len(value) != 2:
            raise ValueError
        items = tuple(value)
        if any(isinstance(item, bool) for item in items):
            raise ValueError
        dimensions = tuple(integer_index(item) for item in items)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"{name} must contain exactly two positive integer dimensions"
        ) from exc
    if any(dimension <= 0 for dimension in dimensions):
        raise ValueError(
            f"{name} must contain exactly two positive integer dimensions"
        )
    return int(dimensions[0]), int(dimensions[1])


class CoordinateMappingUnavailable(ValueError):
    """Raised when a transform chain has no safe, supported point mapping."""


@dataclass(frozen=True, slots=True)
class CoordinateMappingResult:
    status: Literal["mapped", "outside_source", "outside_crop"]
    point: tuple[float, float] | None
    approximate: bool
    contract_version: int = COORDINATE_MAPPING_CONTRACT_VERSION


@dataclass(frozen=True, slots=True, init=False)
class PreprocessCoordinateMap:
    """Compose source → canonical → transformed → crop → output-canvas mapping.

    `source_size` is the EXIF-oriented source pixel size. When a non-identity
    `layout_transform` is supplied, `analysis_is_canonicalized=True` is
    mandatory and `analysis` must have been computed from that canonicalized
    image. Its source_width/source_height must equal
    `layout_transform.canonical_size(source_size)`.

    The constructor takes a deep snapshot of the mutable legacy
    PreprocessAnalysis model. The map and its replay steps are immutable from
    the caller's perspective. It is ephemeral: no fields are added to
    PreprocessAnalysis and no PDIC, PPP, SECTION, crop-plan or image file is
    changed.
    """

    _analysis: PreprocessAnalysis = field(repr=False, compare=False)
    source_size: tuple[int, int]
    raw_source_size: tuple[int, int] | None
    exif_orientation: int
    layout_transform: LayoutTransform
    canvas: OutputCanvasInfo | None
    analysis_is_canonicalized: bool
    _orthogonal_step_cache: tuple[
        tuple[OrthogonalWarpEstimate, float], ...
    ] = field(repr=False, compare=False)

    def __init__(
        self,
        analysis: PreprocessAnalysis,
        source_size: tuple[int, int] | None = None,
        layout_transform: LayoutTransform | None = None,
        canvas: OutputCanvasInfo | None = None,
        analysis_is_canonicalized: bool = False,
        *,
        raw_source_size: Sequence[int] | None = None,
        exif_orientation: int = 1,
    ) -> None:
        snapshot = deepcopy(analysis)
        raw_dimensions = (
            (snapshot.source_width, snapshot.source_height)
            if source_size is None else source_size
        )
        size = _validated_size_pair(raw_dimensions, "source_size")
        try:
            if isinstance(exif_orientation, bool):
                raise TypeError
            orientation = integer_index(exif_orientation)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("exif_orientation must be an integer from 1 through 8") from exc
        if orientation < 1 or orientation > 8:
            raise ValueError("exif_orientation must be an integer from 1 through 8")
        raw_size = (
            None if raw_source_size is None
            else _validated_size_pair(raw_source_size, "raw_source_size")
        )
        if raw_size is None and orientation != 1:
            raise ValueError(
                "raw_source_size is required to validate a non-default EXIF orientation"
            )
        if raw_size is not None:
            expected_size = (raw_size[1], raw_size[0]) if orientation >= 5 else raw_size
            if size != expected_size:
                raise ValueError(
                    "source_size does not match the EXIF-oriented raw_source_size"
                )
        transform = LayoutTransform() if layout_transform is None else layout_transform

        object.__setattr__(self, "_analysis", snapshot)
        object.__setattr__(self, "source_size", size)
        object.__setattr__(self, "raw_source_size", raw_size)
        object.__setattr__(self, "exif_orientation", int(orientation))
        object.__setattr__(self, "layout_transform", transform)
        object.__setattr__(self, "canvas", canvas)
        object.__setattr__(
            self, "analysis_is_canonicalized", bool(analysis_is_canonicalized),
        )
        self._validate()
        object.__setattr__(
            self, "_orthogonal_step_cache", self._build_orthogonal_steps(),
        )

    @property
    def contract_version(self) -> int:
        return COORDINATE_MAPPING_CONTRACT_VERSION

    @property
    def approximate(self) -> bool:
        return bool(self._orthogonal_step_cache)

    def _validate(self) -> None:
        analysis = self._analysis
        if self.source_size[0] <= 0 or self.source_size[1] <= 0:
            raise ValueError("source_size must be positive")
        if not isinstance(self.layout_transform, LayoutTransform):
            raise CoordinateMappingUnavailable("layout transform snapshot is malformed")
        canonical_size = self.layout_transform.canonical_size(self.source_size)
        analysis_size = _validated_size_pair(
            (analysis.source_width, analysis.source_height),
            "analysis source dimensions",
        )
        if canonical_size != analysis_size:
            raise ValueError(
                "analysis dimensions do not match the canonical coordinate frame"
            )
        if (
            self.layout_transform.kind != "identity"
            and not self.analysis_is_canonicalized
        ):
            raise CoordinateMappingUnavailable(
                "non-identity LayoutTransform requires analysis_is_canonicalized=True"
            )

        if str(analysis.geometry_mode or "").strip().casefold() == "uvdoc":
            raise CoordinateMappingUnavailable(
                "UVDoc uses a nonlinear unwarp without a supported point-map contract"
            )

        if len(analysis.crop_box) != 4:
            raise ValueError("crop_box must contain four half-open coordinates")
        x0, y0, x1, y1 = (int(value) for value in analysis.crop_box)
        if (
            x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0
            or x1 > analysis_size[0] or y1 > analysis_size[1]
        ):
            raise ValueError("crop_box is not valid in the transformed image frame")

        if self.canvas is not None and self.canvas.enabled:
            cx0, cy0, cx1, cy1 = self.canvas.content_box
            if (
                cx1 - cx0 != x1 - x0
                or cy1 - cy0 != y1 - y0
                or cx0 < 0 or cy0 < 0
                or cx1 > self.canvas.width or cy1 > self.canvas.height
            ):
                raise ValueError(
                    "canvas content_box must place the complete crop without rescaling"
                )

        if not math.isfinite(float(analysis.applied_angle_deg)):
            raise CoordinateMappingUnavailable("deskew angle is not finite")
        if analysis.perspective_matrix is not None:
            matrix = np.asarray(analysis.perspective_matrix, dtype=float)
            if matrix.size != 9 or not np.isfinite(matrix).all():
                raise CoordinateMappingUnavailable("perspective matrix is malformed")
            try:
                inverse = np.linalg.inv(matrix.reshape(3, 3))
            except np.linalg.LinAlgError as exc:
                raise CoordinateMappingUnavailable(
                    "perspective matrix is singular"
                ) from exc
            if not np.isfinite(inverse).all():
                raise CoordinateMappingUnavailable(
                    "perspective inverse is not finite"
                )
            # Pillow's raster perspective replay normalizes inv(H) by
            # inv(H)[2, 2]. A nonsingular homography may still have a zero
            # bottom-right inverse coefficient and therefore cannot be
            # materialized by our image renderer. Compare relative to the
            # inverse's norm, since a homography has arbitrary scalar scale.
            inverse_scale = float(np.max(np.abs(inverse)))
            if abs(float(inverse[2, 2])) <= 1e-12 * inverse_scale:
                raise CoordinateMappingUnavailable(
                    "perspective inverse cannot be normalized for raster replay"
                )

    @staticmethod
    def _validate_orthogonal_replay_estimate(
        estimate: OrthogonalWarpEstimate,
    ) -> None:
        """Reject applied orthogonal stages whose saved geometry cannot replay."""
        def finite(values: Sequence[float]) -> bool:
            return all(math.isfinite(float(value)) for value in values)

        def increasing(values: Sequence[float]) -> bool:
            return all(
                float(right) > float(left)
                for left, right in zip(values, values[1:])
            )

        y_knots = estimate.y_knots
        angle_knots = estimate.angle_knots_deg
        x_knots = estimate.x_knots
        separator_y = estimate.separator_y_knots
        separator_shift = estimate.separator_shift_knots_px
        row_angles = estimate.row_angle_grid_deg
        row_displacements = estimate.row_displacement_grid_px

        if bool(separator_y) != bool(separator_shift) or (
            separator_y and len(separator_y) != len(separator_shift)
        ):
            raise CoordinateMappingUnavailable(
                "orthogonal replay separator geometry is incomplete"
            )
        if separator_y and (
            not finite(separator_y)
            or not finite(separator_shift)
            or not increasing(separator_y)
        ):
            raise CoordinateMappingUnavailable(
                "orthogonal replay separator geometry is invalid"
            )

        has_row_grid = bool(row_angles or row_displacements)
        if has_row_grid:
            rows = int(estimate.row_grid_rows)
            cols = int(estimate.row_grid_cols)
            if (
                rows < 2 or cols < 2
                or len(y_knots) != rows
                or len(x_knots) != cols
                or not finite(y_knots)
                or not finite(x_knots)
                or not increasing(y_knots)
                or not increasing(x_knots)
                or (row_angles and len(row_angles) != rows * cols)
                or (
                    row_displacements
                    and len(row_displacements) != rows * cols
                )
                or not finite(row_angles)
                or not finite(row_displacements)
            ):
                raise CoordinateMappingUnavailable(
                    "orthogonal replay row-grid geometry is invalid"
                )
            has_row_geometry = True
        else:
            if bool(y_knots) != bool(angle_knots) or (
                y_knots and len(y_knots) != len(angle_knots)
            ):
                raise CoordinateMappingUnavailable(
                    "orthogonal replay legacy row geometry is incomplete"
                )
            if y_knots and (
                not finite(y_knots)
                or not finite(angle_knots)
                or not increasing(y_knots)
            ):
                raise CoordinateMappingUnavailable(
                    "orthogonal replay legacy row geometry is invalid"
                )
            has_row_geometry = bool(y_knots and angle_knots)

        if not math.isfinite(float(estimate.reference_x)):
            raise CoordinateMappingUnavailable(
                "orthogonal replay reference coordinate is not finite"
            )
        if not has_row_geometry and not separator_y:
            raise CoordinateMappingUnavailable(
                "orthogonal replay geometry is missing"
            )

    @classmethod
    def _validate_orthogonal_snapshot(
        cls, estimate: OrthogonalWarpEstimate,
    ) -> None:
        try:
            cls._validate_orthogonal_replay_estimate(estimate)
        except CoordinateMappingUnavailable:
            raise
        except (TypeError, ValueError, OverflowError, IndexError) as exc:
            raise CoordinateMappingUnavailable(
                "orthogonal replay geometry is malformed"
            ) from exc

    def _build_orthogonal_steps(
        self,
    ) -> tuple[tuple[OrthogonalWarpEstimate, float], ...]:
        analysis = self._analysis
        if not analysis.orthogonal_applied:
            return ()
        if analysis.orthogonal_steps:
            steps: list[tuple[OrthogonalWarpEstimate, float]] = []
            for payload in analysis.orthogonal_steps:
                if not isinstance(payload, dict):
                    raise CoordinateMappingUnavailable(
                        "orthogonal replay step is malformed"
                    )
                try:
                    estimate, row_gain = _orthogonal_estimate_from_step(dict(payload))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise CoordinateMappingUnavailable(
                        "orthogonal replay step is malformed"
                    ) from exc
                if not math.isfinite(float(row_gain)):
                    raise CoordinateMappingUnavailable(
                        "orthogonal row gain is not finite"
                    )
                self._validate_orthogonal_snapshot(estimate)
                steps.append((estimate, float(row_gain)))
            return tuple(steps)
        if analysis.orthogonal_y_knots and analysis.orthogonal_angle_knots_deg:
            try:
                estimate = OrthogonalWarpEstimate(
                    y_knots=tuple(analysis.orthogonal_y_knots),
                    angle_knots_deg=tuple(analysis.orthogonal_angle_knots_deg),
                    x_knots=tuple(analysis.orthogonal_x_knots),
                    row_grid_rows=int(analysis.orthogonal_row_grid_rows),
                    row_grid_cols=int(analysis.orthogonal_row_grid_cols),
                    row_angle_grid_deg=tuple(
                        analysis.orthogonal_row_angle_grid_deg
                    ),
                    row_displacement_grid_px=tuple(
                        analysis.orthogonal_row_displacement_grid_px
                    ),
                    separator_y_knots=tuple(
                        analysis.orthogonal_separator_y_knots
                    ),
                    separator_shift_knots_px=tuple(
                        analysis.orthogonal_separator_shift_knots_px
                    ),
                    reference_x=float(analysis.orthogonal_reference_x),
                    active=True,
                )
                row_gain = float(analysis.orthogonal_row_gain)
            except (TypeError, ValueError, OverflowError) as exc:
                raise CoordinateMappingUnavailable(
                    "orthogonal replay legacy geometry is malformed"
                ) from exc
            if not math.isfinite(row_gain):
                raise CoordinateMappingUnavailable(
                    "orthogonal row gain is not finite"
                )
            self._validate_orthogonal_snapshot(estimate)
            return ((estimate, row_gain),)
        raise CoordinateMappingUnavailable(
            "orthogonal replay geometry is missing"
        )

    @staticmethod
    def _normalized_projective_matrix(
        matrix: Sequence[float],
    ) -> tuple[float, ...]:
        """Remove arbitrary homogeneous scale before the shared point mapper.

        The general pixel-point utility clamps denominators below 1e-9 in
        absolute units, whereas H and its inverse can be multiplied by any
        nonzero scalar. Prefer a [2,2] normalizer (as raster replay does for
        the inverse), falling back to the largest coefficient for a forward
        H whose lower-right entry is effectively zero.
        """
        coefficients = np.asarray(matrix, dtype=float).reshape(3, 3)
        magnitude = float(np.max(np.abs(coefficients)))
        scale = float(coefficients[2, 2])
        if abs(scale) <= 1e-12 * magnitude:
            scale = magnitude
        return tuple((coefficients / scale).reshape(-1))

    @staticmethod
    def _projective_denominator_is_unsafe(
        g: float, h: float, i: float, x: float, y: float,
    ) -> bool:
        """Detect a pole relative to its cancelling terms, not absolute scale."""
        terms = (float(g) * float(x), float(h) * float(y), float(i))
        denominator = math.fsum(terms)
        magnitude = math.fsum(abs(term) for term in terms)
        return (
            not math.isfinite(denominator)
            or not math.isfinite(magnitude)
            or magnitude == 0.0
            or abs(denominator) <= 1e-12 * magnitude
        )

    @classmethod
    def _map_projective_point(
        cls, point: tuple[float, float], matrix: Sequence[float],
    ) -> tuple[float, float]:
        """Map one point without the shared helper's absolute 1e-9 clamp.

        Homographies are scale-invariant. A denominator close to zero relative
        to the terms that form it is numerically indistinguishable from a
        projective pole and must not be turned into a plausible in-crop point.
        """
        x, y = float(point[0]), float(point[1])
        coefficients = np.asarray(
            cls._normalized_projective_matrix(matrix), dtype=float,
        ).reshape(3, 3)
        g, h, i = (float(value) for value in coefficients[2])
        if cls._projective_denominator_is_unsafe(g, h, i, x, y):
            raise CoordinateMappingUnavailable(
                "point lies on or too near the projective horizon"
            )
        denominator = math.fsum((g * x, h * y, i))
        a, b, c = (float(value) for value in coefficients[0])
        d, e, f = (float(value) for value in coefficients[1])
        mapped = (
            math.fsum((a * x, b * y, c)) / denominator,
            math.fsum((d * x, e * y, f)) / denominator,
        )
        if not all(math.isfinite(value) for value in mapped):
            raise CoordinateMappingUnavailable(
                "projective point mapping produced a non-finite coordinate"
            )
        return mapped

    def _forward_geometry(self, point: tuple[float, float]) -> tuple[float, float]:
        analysis = self._analysis
        width, height = int(analysis.source_width), int(analysis.source_height)
        x, y = _rotate_point_same_canvas(
            point[0], point[1], width, height,
            float(analysis.applied_angle_deg),
        )
        mapped = np.asarray(((x, y),), dtype=float)
        if analysis.perspective_matrix is not None:
            mapped = np.asarray(
                (self._map_projective_point(
                    (float(mapped[0, 0]), float(mapped[0, 1])),
                    analysis.perspective_matrix,
                ),),
                dtype=float,
            )
        for estimate, row_gain in self._orthogonal_step_cache:
            mapped = transform_points_orthogonal(
                mapped, estimate, row_gain=row_gain, separator_gain=1.0,
            )
        result = (float(mapped[0, 0]), float(mapped[0, 1]))
        if not all(math.isfinite(value) for value in result):
            raise CoordinateMappingUnavailable(
                "forward transform produced a non-finite point"
            )
        return result

    def _inverse_geometry(self, point: tuple[float, float]) -> tuple[float, float]:
        analysis = self._analysis
        mapped = np.asarray((point,), dtype=float)
        for estimate, row_gain in reversed(self._orthogonal_step_cache):
            mapped = inverse_transform_points_orthogonal(
                mapped, estimate, row_gain=row_gain, separator_gain=1.0,
            )
        if analysis.perspective_matrix is not None:
            matrix = np.asarray(
                analysis.perspective_matrix, dtype=float,
            ).reshape(3, 3)
            try:
                inverse = np.linalg.inv(matrix)
            except np.linalg.LinAlgError as exc:
                raise CoordinateMappingUnavailable(
                    "perspective matrix became singular"
                ) from exc
            mapped = np.asarray(
                (self._map_projective_point(
                    (float(mapped[0, 0]), float(mapped[0, 1])),
                    inverse.reshape(-1),
                ),),
                dtype=float,
            )
        width, height = int(analysis.source_width), int(analysis.source_height)
        x, y = _rotate_point_same_canvas(
            float(mapped[0, 0]), float(mapped[0, 1]),
            width, height, -float(analysis.applied_angle_deg),
        )
        if not (math.isfinite(x) and math.isfinite(y)):
            raise CoordinateMappingUnavailable(
                "inverse transform produced a non-finite point"
            )
        return float(x), float(y)

    def _canvas_offset(self) -> tuple[float, float]:
        if self.canvas is None or not self.canvas.enabled:
            return 0.0, 0.0
        return (
            float(self.canvas.content_box[0]),
            float(self.canvas.content_box[1]),
        )

    @staticmethod
    def _point(value: Sequence[float]) -> tuple[float, float]:
        if len(value) != 2:
            raise ValueError("a coordinate point must contain X and Y")
        point = (float(value[0]), float(value[1]))
        if not all(math.isfinite(v) for v in point):
            raise ValueError("coordinate point must be finite")
        return point

    def source_to_output_point(
        self, point: Sequence[float],
    ) -> CoordinateMappingResult:
        x, y = self._point(point)
        source_width, source_height = self.source_size
        if not (0.0 <= x <= source_width - 1 and 0.0 <= y <= source_height - 1):
            return CoordinateMappingResult("outside_source", None, self.approximate)

        canonical = self.layout_transform.source_to_canonical_point(
            x, y, self.source_size,
        )
        tx, ty = self._forward_geometry(
            (float(canonical[0]), float(canonical[1])),
        )
        x0, y0, x1, y1 = (int(value) for value in self._analysis.crop_box)
        if not (x0 <= tx < x1 and y0 <= ty < y1):
            return CoordinateMappingResult("outside_crop", None, self.approximate)
        offset_x, offset_y = self._canvas_offset()
        return CoordinateMappingResult(
            "mapped",
            (tx - x0 + offset_x, ty - y0 + offset_y),
            self.approximate,
        )

    def output_to_source_point(
        self, point: Sequence[float],
    ) -> CoordinateMappingResult:
        x, y = self._point(point)
        offset_x, offset_y = self._canvas_offset()
        x0, y0, x1, y1 = (int(value) for value in self._analysis.crop_box)
        crop_x = x - offset_x
        crop_y = y - offset_y
        if not (
            0.0 <= crop_x < x1 - x0
            and 0.0 <= crop_y < y1 - y0
        ):
            return CoordinateMappingResult("outside_crop", None, self.approximate)

        transformed = (crop_x + x0, crop_y + y0)
        canonical = self._inverse_geometry(transformed)
        source = self.layout_transform.canonical_to_source_point(
            canonical[0], canonical[1], self.source_size,
        )
        source_point = (float(source[0]), float(source[1]))
        source_width, source_height = self.source_size
        if not (
            0.0 <= source_point[0] <= source_width - 1
            and 0.0 <= source_point[1] <= source_height - 1
        ):
            return CoordinateMappingResult(
                "outside_source", None, self.approximate,
            )
        return CoordinateMappingResult(
            "mapped", source_point, self.approximate,
        )

    def _polygon_crosses_perspective_horizon(
        self, source_points: Sequence[Sequence[float]],
    ) -> bool:
        """Refuse ROI edges whose homogeneous denominator crosses zero.

        A vertex-only map cannot certify an entire polygon: both endpoints
        of an edge can lie inside the crop while the segment passes through
        a projective pole. Layout and deskew are affine, so evaluating H's
        last row at their transformed vertices proves whether any straight
        source edge crosses that pole. No persisted coordinates are touched.
        """
        matrix = self._analysis.perspective_matrix
        if matrix is None or len(source_points) < 2:
            return False
        normalized = self._normalized_projective_matrix(matrix)
        g, h, i = normalized[6:]
        width = int(self._analysis.source_width)
        height = int(self._analysis.source_height)
        signs: set[bool] = set()
        for raw_point in source_points:
            x, y = self._point(raw_point)
            canonical = self.layout_transform.source_to_canonical_point(
                x, y, self.source_size,
            )
            tx, ty = _rotate_point_same_canvas(
                float(canonical[0]), float(canonical[1]), width, height,
                float(self._analysis.applied_angle_deg),
            )
            if self._projective_denominator_is_unsafe(g, h, i, tx, ty):
                return True
            denominator = math.fsum((g * tx, h * ty, i))
            signs.add(denominator > 0.0)
            if len(signs) > 1:
                return True
        return False

    def _polygon_edge_samples(
        self, points: Sequence[Sequence[float]],
    ) -> tuple[tuple[float, float], ...]:
        """Sample nonlinear orthogonal edges before certifying domain bounds.

        Homography/deskew alone maps straight segments to straight segments
        (provided no projective horizon is crossed). Orthogonal replay is
        nonlinear, so valid vertices do not prove that the intervening edge
        remains inside the crop/source rectangle. Sample at a bounded interval
        and fail closed rather than returning an unchecked polygon.
        """
        vertices = tuple(self._point(point) for point in points)
        if len(vertices) < 2 or not self._orthogonal_step_cache:
            return vertices
        samples: list[tuple[float, float]] = []
        for index, start in enumerate(vertices):
            end = vertices[(index + 1) % len(vertices)]
            distance = math.hypot(end[0] - start[0], end[1] - start[1])
            steps = max(
                2,
                int(math.ceil(distance / _ORTHOGONAL_POLYGON_SAMPLE_SPACING_PX)),
            )
            if steps % 2:
                steps += 1
            if (
                steps > _ORTHOGONAL_POLYGON_MAX_EDGE_STEPS
                or len(samples) + steps > _ORTHOGONAL_POLYGON_MAX_TOTAL_SAMPLES
            ):
                raise CoordinateMappingUnavailable(
                    "orthogonal polygon edge exceeds the bounded sampling budget"
                )
            fractions = {step / steps for step in range(steps)}
            delta_x = end[0] - start[0]
            delta_y = end[1] - start[1]
            # The warp is piecewise interpolated at these saved coordinates.
            # Include their crossings explicitly so a narrow local excursion
            # cannot hide between the uniform spatial samples. Earlier stages
            # may rotate/warp the edge, so the bounded uniform samples remain
            # necessary as a second, independent coverage layer.
            for estimate, _row_gain in self._orthogonal_step_cache:
                if delta_y != 0.0:
                    for knot in (*estimate.y_knots, *estimate.separator_y_knots):
                        fraction = (float(knot) - start[1]) / delta_y
                        if 0.0 < fraction < 1.0:
                            fractions.add(fraction)
                if delta_x != 0.0:
                    for knot in estimate.x_knots:
                        fraction = (float(knot) - start[0]) / delta_x
                        if 0.0 < fraction < 1.0:
                            fractions.add(fraction)
            if (
                len(fractions) > _ORTHOGONAL_POLYGON_MAX_EDGE_STEPS
                or len(samples) + len(fractions) > _ORTHOGONAL_POLYGON_MAX_TOTAL_SAMPLES
            ):
                raise CoordinateMappingUnavailable(
                    "orthogonal polygon edge exceeds the bounded sampling budget"
                )
            for fraction in sorted(fractions):
                samples.append((
                    start[0] + delta_x * fraction,
                    start[1] + delta_y * fraction,
                ))
        return tuple(samples)

    def source_to_output_polygon(
        self, points: Sequence[Sequence[float]],
    ) -> tuple[tuple[float, float], ...] | None:
        if len(points) == 0 or self._polygon_crosses_perspective_horizon(points):
            return None
        samples = self._polygon_edge_samples(points)
        for sample in samples:
            item = self.source_to_output_point(sample)
            if item.status != "mapped" or item.point is None:
                return None
        mapped = tuple(self.source_to_output_point(point) for point in points)
        if not mapped or any(item.status != "mapped" or item.point is None for item in mapped):
            return None
        return tuple(item.point for item in mapped if item.point is not None)

    def output_to_source_polygon(
        self, points: Sequence[Sequence[float]],
    ) -> tuple[tuple[float, float], ...] | None:
        if len(points) == 0:
            return None
        samples = self._polygon_edge_samples(points)
        mapped_samples = tuple(self.output_to_source_point(point) for point in samples)
        if any(
            item.status != "mapped" or item.point is None
            for item in mapped_samples
        ):
            return None
        source_samples = tuple(
            item.point for item in mapped_samples if item.point is not None
        )
        if self._polygon_crosses_perspective_horizon(source_samples):
            return None
        mapped = tuple(self.output_to_source_point(point) for point in points)
        if not mapped or any(item.status != "mapped" or item.point is None for item in mapped):
            return None
        return tuple(item.point for item in mapped if item.point is not None)
