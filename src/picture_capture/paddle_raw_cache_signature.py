"""Exact normalized Paddle OCR-input fingerprint independent of parser settings."""
from __future__ import annotations
import hashlib
import json
from typing import Any
from PIL import Image
from .models import AppSettings


def cache_signature(image: Image.Image, geometry: Any, settings: AppSettings, *, image_fingerprint: Any, paddle_language: Any, raw_threshold: float) -> str:
    # Only OCR-input-affecting settings belong here. Candidate rules are
    # intentionally omitted so users can tune regex/weights and reuse cached
    # raw OCR without re-running the model.
    data = {
        "version": 4,
        "image_size": list(image.size),
        "image_fingerprint": image_fingerprint(image),
        "layout_transform": geometry.transform.kind,
        "paths": [path.points for path in geometry.column_paths],
        "geometry_top": int(geometry.top),
        "geometry_bottom": int(geometry.bottom),
        "column_widths": [int(value) for value in getattr(geometry, "column_widths", [])],
        "configured_column_width": int(getattr(settings, "column_width", 0) or 0),
        "band_width_semantics": "effective_column_ratio_v2",
        "band_width_ratio": max(1.0, min(100.0, float(getattr(settings, "paddle_band_width_ratio", 100.0)))),
        "band_left_margin": settings.paddle_band_left_margin,
        "language": paddle_language(settings),
        "device": settings.paddle_device,
        "ocr_version": settings.paddle_ocr_version,
        "preprocessing": str(getattr(settings, "paddle_preprocessing", "original")),
        "max_input_side": int(getattr(settings, "paddle_max_input_side", 2800)),
        "use_textline_orientation": bool(getattr(settings, "paddle_use_textline_orientation", False)),
        "raw_rec_threshold": raw_threshold,
        "use_paddleocr": bool(getattr(settings, "paddle_use_paddleocr", True)),
    }
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


