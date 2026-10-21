"""Reversible mapping between source pixels and canonical layout geometry.

Layout analysis may mirror or rotate a page, but OCR and persisted PDIC points
remain in the original source-image coordinate system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageOps

LayoutTransformKind = Literal["identity", "mirror_x", "rotate_ccw90", "rotate_cw90"]
Box = tuple[int, int, int, int]
Point = tuple[int, int]


@dataclass(frozen=True, slots=True)
class LayoutTransform:
    kind: LayoutTransformKind = "identity"

    def __post_init__(self) -> None:
        if self.kind not in {"identity", "mirror_x", "rotate_ccw90", "rotate_cw90"}:
            raise ValueError(f"Unsupported layout transform: {self.kind}")

    def canonical_size(self, source_size: tuple[int, int]) -> tuple[int, int]:
        width, height = source_size
        return (height, width) if self.kind.startswith("rotate_") else (width, height)

    def source_to_canonical_point(self, x: int, y: int, source_size: tuple[int, int]) -> Point:
        width, height = source_size
        if self.kind == "identity":
            return x, y
        if self.kind == "mirror_x":
            return width - 1 - x, y
        if self.kind == "rotate_ccw90":
            return y, width - 1 - x
        return height - 1 - y, x

    def canonical_to_source_point(self, u: int, v: int, source_size: tuple[int, int]) -> Point:
        width, height = source_size
        if self.kind == "identity":
            return u, v
        if self.kind == "mirror_x":
            return width - 1 - u, v
        if self.kind == "rotate_ccw90":
            return width - 1 - v, u
        return v, height - 1 - u

    def source_box_to_canonical(self, box: Box, source_size: tuple[int, int]) -> Box:
        """Map a half-open PIL box without losing its width or height."""
        x0, y0, x1, y1 = box
        width, height = source_size
        if self.kind == "identity":
            return box
        if self.kind == "mirror_x":
            return width - x1, y0, width - x0, y1
        if self.kind == "rotate_ccw90":
            return y0, width - x1, y1, width - x0
        return height - y1, x0, height - y0, x1

    def canonical_box_to_source(self, box: Box, source_size: tuple[int, int]) -> Box:
        u0, v0, u1, v1 = box
        width, height = source_size
        if self.kind == "identity":
            return box
        if self.kind == "mirror_x":
            return width - u1, v0, width - u0, v1
        if self.kind == "rotate_ccw90":
            return width - v1, u0, width - v0, u1
        return v0, height - u1, v1, height - u0

    def canonical_image_for_analysis(self, source: Image.Image) -> Image.Image:
        if self.kind == "identity":
            return source.copy()
        if self.kind == "mirror_x":
            return ImageOps.mirror(source)
        if self.kind == "rotate_ccw90":
            return source.transpose(Image.Transpose.ROTATE_90)
        return source.transpose(Image.Transpose.ROTATE_270)

    def canonical_marker_to_source(
        self, start: Point, end: Point, source_size: tuple[int, int]
    ) -> tuple[Point, Point]:
        """Inverse-map a canonical marker; rotated markers become vertical."""
        return self.canonical_segment_to_source(start, end, source_size)

    def canonical_segment_to_source(
        self, start: Point, end: Point, source_size: tuple[int, int]
    ) -> tuple[Point, Point]:
        return (
            self.canonical_to_source_point(*start, source_size),
            self.canonical_to_source_point(*end, source_size),
        )

    def source_segment_to_canonical(
        self, start: Point, end: Point, source_size: tuple[int, int]
    ) -> tuple[Point, Point]:
        return (
            self.source_to_canonical_point(*start, source_size),
            self.source_to_canonical_point(*end, source_size),
        )
