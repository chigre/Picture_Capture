#!/usr/bin/env python3
"""Read-only Markdown/JSON comparison of existing benchmark reports.

Never combines historical cache F1 with current detector F1 into one score.
Example:
  python scripts/quality_report.py historical_audit.json current_scan.json \
    --json-output summary.json --markdown-output summary.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from picture_capture.quality.benchmark_provenance import (
    build_quality_report, markdown_quality_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    sources = [
        (p.name, json.loads(p.read_text(encoding="utf-8")))
        for p in args.inputs
    ]
    result = build_quality_report(sources)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + chr(10),
        encoding="utf-8",
    )
    args.markdown_output.write_text(
        markdown_quality_report(result), encoding="utf-8",
    )
    print(args.json_output)
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
