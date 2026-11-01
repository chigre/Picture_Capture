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
    ) -> None:
        snapshot = deepcopy(analysis)
        raw_size = source_size or (
            int(snapshot.source_width),
            int(snapshot.source_height),
        )
        if len(raw_size) != 2:
            raise ValueError("source_size must contain width and height")
        size = (int(raw_size[0]), int(raw_size[1]))
        transform = layout_transform or LayoutTransform()

        object.__setattr__(self, "_analysis", snapshot)
        object.__setattr__(self, "source_size", size)
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
        canonical_size = self.layout_transform.canonical_size(self.source_size)
        analysis_size = (
            int(analysis.source_width),
            int(analysis.source_height),
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
                estimate, row_gain = _orthogonal_estimate_from_step(dict(payload))
                if not math.isfinite(float(row_gain)):
                    raise CoordinateMappingUnavailable(
                        "orthogonal row gain is not finite"
                    )
                steps.append((estimate, float(row_gain)))
            return tuple(steps)
        if analysis.orthogonal_y_knots and analysis.orthogonal_angle_knots_deg:
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
            return ((estimate, float(analysis.orthogonal_row_gain)),)
        return ()

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

    def source_to_output_polygon(
        self, points: Sequence[Sequence[float]],
    ) -> tuple[tuple[float, float], ...] | None:
        mapped = tuple(self.source_to_output_point(point) for point in points)
        if not mapped or any(item.status != "mapped" or item.point is None for item in mapped):
            return None
        if self._polygon_crosses_perspective_horizon(points):
            return None
        return tuple(item.point for item in mapped if item.point is not None)

    def output_to_source_polygon(
        self, points: Sequence[Sequence[float]],
    ) -> tuple[tuple[float, float], ...] | None:
        mapped = tuple(self.output_to_source_point(point) for point in points)
        if not mapped or any(item.status != "mapped" or item.point is None for item in mapped):
            return None
        source_vertices = tuple(
            item.point for item in mapped if item.point is not None
        )
        if self._polygon_crosses_perspective_horizon(source_vertices):
            return None
        return source_vertices
