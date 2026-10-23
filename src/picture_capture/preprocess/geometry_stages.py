"""Optional image geometry stages used by the public preprocessing facade.

The caller supplies its current detector/unwarper at invocation time. These
working-image results are not serialized, and this leaf does not import the GUI
or the public image_preprocessing facade.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class ExplicitUnwarpResult:
    image: Image.Image
    polygons: list[np.ndarray]
    geometry_mode: str


@dataclass(frozen=True)
class PostPerspectiveRedetection:
    polygons: list[np.ndarray]
    redetected: bool


def apply_explicit_uvdoc(
    image: Image.Image,
    polygons: list[np.ndarray],
    actual_geometry_mode: str,
    *,
    requested_geometry_mode: str,
    document_unwarper: Callable[[Image.Image], Image.Image],
    warnings: list[str],
    method_parts: list[str],
) -> ExplicitUnwarpResult:
    """Keep the user-only UVDoc fallback and its failure/partial-state policy."""
    if requested_geometry_mode == "uvdoc":
        try:
            image = document_unwarper(image)
            polygons = []
            actual_geometry_mode = "uvdoc"
            method_parts.append("uvdoc")
        except Exception as exc:
            warnings.append(
                f"Paddle UVDoc 展平不可用，已保留前一步几何结果：{exc}"
            )
    return ExplicitUnwarpResult(image, polygons, actual_geometry_mode)


def redetect_after_perspective(
    image: Image.Image,
    polygons: list[np.ndarray],
    settings: object,
    *,
    requested_geometry_mode: str,
    actual_geometry_mode: str,
    text_detector: Callable[..., object],
    min_boxes: int,
    warnings: list[str],
    method_parts: list[str],
) -> PostPerspectiveRedetection:
    """Re-detect actual warped pixels only for a successful automatic perspective."""
    if (
        requested_geometry_mode == "auto"
        and actual_geometry_mode == "perspective"
        and polygons
    ):
        try:
            detected = text_detector(image, settings)
            if len(detected) >= min_boxes:
                polygons = [
                    np.asarray(poly, dtype=float)
                    for poly in detected
                ]
                method_parts.append("post_perspective_redetect")
                return PostPerspectiveRedetection(polygons, True)
            else:
                warnings.append(
                    "透视后正文复检文本框不足，正交细化沿用变换后的原检测框。"
                )
        except Exception as exc:
            warnings.append(
                f"透视后正文复检不可用，正交细化沿用变换后的原检测框：{exc}"
            )
    return PostPerspectiveRedetection(polygons, False)
