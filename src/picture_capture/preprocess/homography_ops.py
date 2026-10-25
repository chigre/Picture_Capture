"""Canonical no-Tk homography and scanner-paper warp primitives.

Pure matrix/coordinate operations stay here, while historical geometry, deskew
and orthogonal entrypoints supply current call-time normalization/crop hooks.
This owner intentionally does not import any GUI, pipeline or public facade.
"""
from __future__ import annotations

from typing import Callable, Iterable

import numpy as np
from PIL import Image


def homography_jacobian(
    matrix: Iterable[float], x: float, y: float,
) -> np.ndarray:
    """Return the analytic 2x2 Jacobian of a 3x3 homography at source XY."""
    mat = np.asarray(tuple(matrix), dtype=float).reshape(3, 3)
    a, b, c = mat[0]
    d, e, f = mat[1]
    g, h, i = mat[2]
    denominator = g * float(x) + h * float(y) + i
    if abs(denominator) < 1e-9:
        raise ValueError("Homography Jacobian is singular at the requested point")
    numerator_u = a * float(x) + b * float(y) + c
    numerator_v = d * float(x) + e * float(y) + f
    denom_sq = denominator * denominator
    return np.asarray(
        [
            [
                (a * denominator - g * numerator_u) / denom_sq,
                (b * denominator - h * numerator_u) / denom_sq,
            ],
            [
                (d * denominator - g * numerator_v) / denom_sq,
                (e * denominator - h * numerator_v) / denom_sq,
            ],
        ],
        dtype=float,
    )


def solve_quad_homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Return a 3x3 matrix mapping src XY coordinates to dst XY coordinates."""
    if src.shape != (4, 2) or dst.shape != (4, 2):
        raise ValueError("Homography requires four 2D source and destination points")
    rows: list[list[float]] = []
    values: list[float] = []
    for (x, y), (u, v) in zip(src, dst):
        rows.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
        values.append(u)
        rows.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
        values.append(v)
    coeff = np.linalg.solve(np.asarray(rows, dtype=float), np.asarray(values, dtype=float))
    matrix = np.asarray(
        [
            [coeff[0], coeff[1], coeff[2]],
            [coeff[3], coeff[4], coeff[5]],
            [coeff[6], coeff[7], 1.0],
        ],
        dtype=float,
    )
    return matrix


def transform_points_homography(points: np.ndarray, matrix: Iterable[float]) -> np.ndarray:
    mat = np.asarray(tuple(matrix), dtype=float).reshape(3, 3)
    raw = np.asarray(points, dtype=float)
    flat = raw.reshape(-1, 2)
    hom = np.column_stack([flat, np.ones(len(flat), dtype=float)])
    mapped = hom @ mat.T
    denom = mapped[:, 2:3]
    denom[np.abs(denom) < 1e-9] = 1e-9
    xy = mapped[:, :2] / denom
    return xy.reshape(raw.shape)


def transform_polygons_homography(
    polygons: Iterable[np.ndarray], matrix: Iterable[float],
    *, transform_points: Callable[[np.ndarray, Iterable[float]], np.ndarray],
) -> list[np.ndarray]:
    return [
        transform_points(np.asarray(poly, dtype=float), matrix)
        for poly in polygons
    ]


def corner_paper_fill(
    image: Image.Image, *, normalize_page_rgb: Callable[[Image.Image], Image.Image],
) -> tuple[int, int, int]:
    source = normalize_page_rgb(image)
    w, h = source.size
    pw = max(1, round(w * 0.04))
    ph = max(1, round(h * 0.04))
    samples = [
        np.asarray(source.crop((0, 0, pw, ph)), dtype=np.uint8).reshape(-1, 3),
        np.asarray(source.crop((max(0, w - pw), 0, w, ph)), dtype=np.uint8).reshape(-1, 3),
        np.asarray(source.crop((0, max(0, h - ph), pw, h)), dtype=np.uint8).reshape(-1, 3),
        np.asarray(source.crop((max(0, w - pw), max(0, h - ph), w, h)), dtype=np.uint8).reshape(-1, 3),
    ]
    median = np.median(np.concatenate(samples, axis=0), axis=0)
    return tuple(int(round(v)) for v in median[:3])


def apply_homography_image(
    image: Image.Image, matrix: Iterable[float], *,
    normalize_page_rgb: Callable[[Image.Image], Image.Image],
    paper_fill: Callable[[Image.Image], tuple[int, int, int]],
) -> Image.Image:
    source = normalize_page_rgb(image)
    mat = np.asarray(tuple(matrix), dtype=float).reshape(3, 3)
    inverse = np.linalg.inv(mat)
    inverse /= inverse[2, 2]
    coeff = (
        float(inverse[0, 0]), float(inverse[0, 1]), float(inverse[0, 2]),
        float(inverse[1, 0]), float(inverse[1, 1]), float(inverse[1, 2]),
        float(inverse[2, 0]), float(inverse[2, 1]),
    )
    return source.transform(
        source.size,
        Image.Transform.PERSPECTIVE,
        coeff,
        resample=Image.Resampling.BICUBIC,
        fillcolor=paper_fill(source),
    )
