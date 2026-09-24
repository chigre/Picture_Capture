#!/usr/bin/env python3
"""Run local Profile-v3 layout regression pages without committing scan fixtures.

Expected input layout: ROOT/<validated-example-name>/*.{png,jpg,tif,...}. Results
are written outside the scan tree as JSON plus optional lightweight overlays.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from picture_capture.dictionary_profile import language_effective_settings, profile_library_path  # noqa: E402
from picture_capture.coordinate_space import CANONICAL_COORDINATE_SPACE  # noqa: E402
from picture_capture.image_utils import normalize_page_rgb  # noqa: E402
from picture_capture.layout_detection import detect_layout_parameters  # noqa: E402
from picture_capture.models import IMAGE_EXTENSIONS, AppSettings  # noqa: E402
from picture_capture.processing import derive_geometry, detect_entries  # noqa: E402


def _settings(example: dict) -> AppSettings:
    layout = dict(example.get("layout") or {})
    language = str(example.get("language") or "eng")
    writing = str(layout.get("writing_mode") or "horizontal-tb")
    direction = str(layout.get("text_direction") or "ltr")
    transform = "rotate_ccw90" if writing == "vertical-rl" else "rotate_cw90" if writing == "vertical-lr" else "mirror_x" if direction == "rtl" else "identity"
    settings = AppSettings(
        columns=int(layout.get("columns") or 1),
        layout_columns_policy=str(layout.get("columns_policy") or "detect"),
        layout_column_separator_mode=str(layout.get("column_separator") or "auto"),
        layout_writing_mode=writing,
        layout_text_direction=direction,
        layout_transform=transform,
        analysis_threshold_mode=str(layout.get("analysis_threshold_mode") or "auto"),
        ocr_language=language,
    )
    for key, value in language_effective_settings(language, writing).items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    settings.detection_method = "left_edge"
    return settings


def _overlay(image: Image.Image, settings: AppSettings, entries, output: Path) -> None:
    canvas = normalize_page_rgb(image).copy()
    draw = ImageDraw.Draw(canvas)
    geometry = derive_geometry(canvas, settings)
    for path in geometry.column_paths:
        points = [geometry.canonical_to_source(x, y) for y, x in path.points]
        if len(points) >= 2:
            draw.line(points, fill=(255, 0, 0), width=3)
    for entry in entries:
        _u, v = geometry.source_to_canonical(entry.x, entry.y)
        column = min(range(len(geometry.column_starts)), key=lambda i: abs(geometry.column_starts[i] - _u))
        start = (geometry.x_at(column, v), v)
        end = (start[0] + geometry.column_widths[column], v)
        draw.line(geometry.transform.canonical_marker_to_source(start, end, image.size), fill=(0, 180, 255), width=3)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.thumbnail((1400, 1400))
    canvas.save(output, "PNG")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scan_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--overlays", action="store_true")
    args = parser.parse_args()
    library = json.loads(profile_library_path().read_text(encoding="utf-8"))
    diagnostics = []
    for name, example in library["validated_examples"].items():
        folder = args.scan_root / name
        if not folder.is_dir():
            diagnostics.append({"dictionary": name, "status": "missing_fixture"})
            continue
        settings = _settings(example)
        for path in sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS):
            with Image.open(path) as opened:
                image = normalize_page_rgb(opened)
            estimate = detect_layout_parameters(image, settings)
            entries, geometry = detect_entries(image, settings)
            marker = geometry.transform.canonical_marker_to_source((10, 10), (50, 10), image.size)
            orientation = "vertical" if marker[0][0] == marker[1][0] else "horizontal"
            row = {
                "format": "picture-capture-profile-diagnostics-v2",
                "dictionary": name,
                "page": path.name,
                "detected_columns": estimate.columns,
                "layout_coordinate_space": CANONICAL_COORDINATE_SPACE,
                "canonical_page_width": int(estimate.canonical_width or geometry.transform.canonical_size(image.size)[0]),
                "column_start_u": estimate.manual_x,
                "column_width_u": estimate.column_width,
                "gutter_u": estimate.gutter,
                "separator_u": estimate.separator_x,
                "canonical_transform": estimate.canonical_transform,
                "entry_count": len(entries),
                "marker_orientation": orientation,
                "ocr_language": settings.tesseract_language or settings.ocr_language,
                "ocr_backend": settings.ocr_engine,
            }
            diagnostics.append(row)
            if args.overlays:
                _overlay(image, settings, entries, args.output / "overlays" / name / f"{path.stem}.png")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
