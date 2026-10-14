"""Isolated multiresolution geometry benchmark; never writes PPP/PDIC.

Usage:
  python scripts/benchmark_layout_scales.py --settings PATH.json --images D:/scans/001.png D:/scans/002.png --output D:/benchmark/scales.json

This compares estimated layout geometry, NOT ordinary drawing equivalence.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from time import perf_counter

from PIL import Image

# Support invocation from the repository checkout without pip installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from picture_capture.image_utils import normalize_page_rgb
from picture_capture.layout_detection import detect_layout_parameters, clear_layout_estimate_cache
from picture_capture.models import AppSettings


def _scaled_settings(settings: AppSettings, scale: float) -> AppSettings:
    effective = replace(settings)
    # Pixel-based controls must be scaled alongside the source domain.
    for key in (
        "start_y", "bottom_y", "manual_x", "column_width", "gutter",
        "character_height", "row_padding",
    ):
        value = getattr(effective, key, None)
        if isinstance(value, (int, float)):
            setattr(effective, key, max(1, round(float(value) * scale))
                    if key in {"character_height", "column_width"} else
                    max(0, round(float(value) * scale)))
    offsets = getattr(effective, "column_start_offsets", None)
    if offsets:
        effective.column_start_offsets = [
            round(float(value) * scale) for value in offsets
        ]
    return effective


def _estimate_record(estimate, scale: float) -> dict:
    def src(value):
        return round(float(value) / scale, 2)
    return {
        "columns": int(estimate.columns),
        "manual_x_source": src(estimate.manual_x),
        "start_y_source": src(estimate.start_y),
        "column_width_source": src(estimate.column_width),
        "gutter_source": src(estimate.gutter),
        "character_height_source": src(estimate.character_height),
        "method": str(getattr(estimate, "method", "")),
    }


def run(settings: AppSettings, image_paths: list[Path]) -> list[dict]:
    records = []
    for image_path in image_paths:
        with Image.open(image_path) as opened:
            source = normalize_page_rgb(opened)
        try:
            for scale in (1.0, 0.75, 0.5):
                clear_layout_estimate_cache()
                work = source if scale == 1.0 else source.resize(
                    (round(source.width * scale), round(source.height * scale)),
                    Image.Resampling.BILINEAR,
                )
                try:
                    scaled_settings = _scaled_settings(settings, scale)
                    started = perf_counter()
                    estimate = detect_layout_parameters(work, scaled_settings)
                    elapsed = perf_counter() - started
                    records.append({
                        "page": image_path.name,
                        "scale": scale,
                        "input_size": list(work.size),
                        "seconds": round(elapsed, 4),
                        "estimate": _estimate_record(estimate, scale),
                    })
                finally:
                    if work is not source:
                        work.close()
        finally:
            source.close()
    return records


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, required=True,
                        help="Project AppSettings JSON")
    parser.add_argument("--images", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    settings = AppSettings.from_json(args.settings)
    output = run(settings, args.images)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    for row in output:
        print(f"{row['page']} {int(row['scale'] * 100)}% "
              f"{row['seconds']:.3f}s {row['estimate']}")
    print(f"Saved {args.output}; PDIC/PPP untouched. "
          "A change in estimates requires full PDIC parity validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
