#!/usr/bin/env python3
"""Check actual 2026-10-10 dictionary review crops (never train on the labels).

Usage:
  python scripts/validate_real_scan_rois.py --assets /path/to/unzipped/assets

The ZIP contains editorially annotated image *crops*, not raw 3240x4600 source
pages. We remove the red review annotation strokes before measuring pixels.
This verifies local visual evidence, NOT whole-page recall/F1 or a PDIC result.
The scan crops themselves are deliberately NOT distributed in this repository.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from picture_capture.illustration_detection import _rle_components
from picture_capture.ordinary_bracket_pair import _bracket_side
from picture_capture.visual_boundary_locator import safe_gap_above


# First number is expected visible real bracketed entries; second records
# approximate annotation-free local opening-bracket tops (not source PDIC Y).
CROPS = {
    "040082_1391_correction.jpg": (2, (155, 237)),
    "040082_1886_correction.jpg": (1, (154,)),
    "040086_662_correction.jpg": (1, (152,)),
    "040088_1559_correction.jpg": (1, (233,)),
}


def analyze_crop(path: Path) -> dict:
    with Image.open(path) as opened:
        rgb = np.asarray(opened.convert("RGB")).astype(np.float32)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    annotation = (r > 110) & (r > g * 1.35) & (r > b * 1.35)
    gray = rgb.mean(axis=2)
    gray[annotation] = 255.0
    ink = gray < 170.0
    openings = []
    closings = []
    for x0, y0, x1, y1, area in _rle_components(ink):
        width, height = x1 - x0, y1 - y0
        if not (18 <= width <= 55 and 42 <= height <= 100 and area >= 100):
            continue
        component = ink[y0:y1, x0:x1]
        if _bracket_side(component, True):
            openings.append((x0, y0, width, height))
        if _bracket_side(component, False):
            closings.append((x0, y0, width, height))

    pairs = []
    for opener in openings:
        ax, ay, _, ah = opener
        if not (130 <= ax <= 180 and ay >= 120):
            continue
        if any(
            90 <= bx - ax <= 350
            and abs(by - ay) <= 20
            and abs(bh - ah) <= 25
            for bx, by, _bw, bh in closings
        ):
            # These are 1015x410 local review screenshots. Keep them distinct
            # from original image or PDIC coordinates at 3240x4600.
            gap = safe_gap_above(
                gray[:, 90:980].astype(np.uint8), ay, 50,
            )
            pairs.append({"bracket_top_crop_y": ay, "gap_crop_y": gap})
    pairs.sort(key=lambda item: item["bracket_top_crop_y"])
    return {"crop": path.name, "pairs": pairs}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    output = []
    for name, (expected_count, expected_ys) in CROPS.items():
        path = args.assets / name
        if not path.is_file():
            parser.error(f"Real review crop not found: {path}")
        row = analyze_crop(path)
        tops = [item["bracket_top_crop_y"] for item in row["pairs"]]
        row["expected_entries"] = expected_count
        row["matches_expected"] = (
            len(tops) == expected_count
            and all(abs(actual - expected) <= 10
                    for actual, expected in zip(tops, expected_ys))
            # For 040088 the actual CJK entry is below the figure caption.
            and (name != "040088_1559_correction.jpg" or all(y > 210 for y in tops))
        )
        output.append(row)
    report = {
        "format": "picture-capture-real-review-crop-audit-v1",
        "whole_page_metric": False,
        "annotation": "editorial red marks removed for pixel analysis",
        "crops": output,
        "passed": all(row["matches_expected"] for row in output),
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
