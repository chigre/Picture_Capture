"""Layout detection compatibility facade with reliability fusion enabled.

The original detector implementation is kept in layout_detection_legacy.py so
all existing public/private helpers and test monkeypatch points remain available.

Layout is no longer the owner of page denoising.  It consumes the same
full-resolution, coordinate-identical analysis image as ordinary drawing and
Page Understanding.  The reliability layer may still apply its stricter
layout-specific speck guard afterwards, but every detector now starts from one
shared cleaned page.
"""
from __future__ import annotations

import sys

from . import layout_detection_legacy as _legacy
from .image_utils import build_analysis_image

for _name in dir(_legacy):
    if _name.startswith("__") or _name == "detect_layout_parameters":
        continue
    globals()[_name] = getattr(_legacy, _name)

_legacy_detect_layout_parameters = _legacy.detect_layout_parameters


def detect_layout_parameters(image, settings):
    from .layout_reliability import detect_layout_parameters_reliable

    analysis_image = build_analysis_image(image, settings)
    return detect_layout_parameters_reliable(
        analysis_image, settings, sys.modules[__name__]
    )
