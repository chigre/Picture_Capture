"""Canonical geometry dataclasses with historical pickle identity maintained by processing_core.

Do not import processing_core here: it re-exports these exact class objects
and restores their original module identity after import.
"""
from __future__ import annotations
from dataclasses import dataclass
from .layout_transform import LayoutTransform


@dataclass(slots=True)
class ColumnPath:
    """Piecewise-linear left edge of one dictionary column."""

    points: list[tuple[int, int]]

    def x_at(self, y: int) -> int:
        if not self.points:
            return 0
        if y <= self.points[0][0]:
            return self.points[0][1]
        if y >= self.points[-1][0]:
            return self.points[-1][1]
        for (y0, x0), (y1, x1) in zip(self.points, self.points[1:]):
            if y0 <= y <= y1:
                if y1 == y0:
                    return x0
                ratio = (y - y0) / (y1 - y0)
                return round(x0 + ratio * (x1 - x0))
        return self.points[-1][1]

    def x_bounds(self, y0: int, y1: int) -> tuple[int, int]:
        samples = [self.x_at(y0), self.x_at(y1)]
        samples.extend(x for y, x in self.points if y0 <= y <= y1)
        return min(samples), max(samples)


@dataclass(slots=True)
class Geometry:
    column_starts: list[int]
    column_widths: list[int]
    top: int
    bottom: int
    column_paths: list[ColumnPath]
    transform: LayoutTransform = LayoutTransform()
    source_size: tuple[int, int] = (0, 0)

    def x_at(self, column: int, y: int) -> int:
        if 0 <= column < len(self.column_paths):
            return self.column_paths[column].x_at(y)
        return self.column_starts[column]

    def x_bounds(self, column: int, y0: int, y1: int) -> tuple[int, int]:
        if 0 <= column < len(self.column_paths):
            return self.column_paths[column].x_bounds(y0, y1)
        x = self.column_starts[column]
        return x, x

    def source_to_canonical(self, x: int, y: int) -> tuple[int, int]:
        if self.source_size == (0, 0):
            return x, y
        return self.transform.source_to_canonical_point(x, y, self.source_size)

    def canonical_to_source(self, x: int, y: int) -> tuple[int, int]:
        if self.source_size == (0, 0):
            return x, y
        return self.transform.canonical_to_source_point(x, y, self.source_size)
