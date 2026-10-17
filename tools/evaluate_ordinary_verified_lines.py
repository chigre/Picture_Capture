#!/usr/bin/env python3
"""Evaluate a unified Layout export against explicitly reviewed page lines.

Usage:
    python tools/evaluate_ordinary_verified_lines.py \
        Page009_v2.json Page009_reviewed_lines.json \
        --tolerance 12

The reviewed file must use:
{
  "schema": "picture-capture-human-reviewed-lines-v1",
  "human_verified": true,
  "image_size": [1388, 2156],
  "lines": [{"x": 0, "y": 83}, ...]
}
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Make direct invocation from a source checkout work without installing pip.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from picture_capture.quality.ordinary_verified_evaluation import evaluate_ordinary_page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagnostic", type=Path)
    parser.add_argument("reviewed", type=Path)
    parser.add_argument("--tolerance", type=int, default=12)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        diagnostic = json.loads(args.diagnostic.read_text(encoding="utf-8"))
        verified = json.loads(args.reviewed.read_text(encoding="utf-8"))
        result = evaluate_ordinary_page(
            diagnostic, verified, tolerance_px=args.tolerance,
        )
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
