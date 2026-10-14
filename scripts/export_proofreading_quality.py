#!/usr/bin/env python3
"""Explicit local-only export of proofreading *quality metadata*, never labels.

Use --journal from a project-local ProofreadingEvidence sidecar and its
corresponding saved PDIC. No network use; no OCR images or words are exported.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from picture_capture.formats import write_text_atomic
from picture_capture.proofreading_quality_export import summarize_local_events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--pdic", type=Path, required=True)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--license-statement", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize_local_events(
        args.journal, args.pdic, image_path=args.image,
        project_id=args.project_id, license_statement=args.license_statement,
    )
    protected = {args.pdic.resolve(), args.journal.resolve()}
    if args.image is not None:
        protected.add(args.image.resolve())
    if args.output.resolve() in protected:
        parser.error("The export must not overwrite a source PDIC, image or event journal")
    if args.output.suffix.lower() != ".json" or args.output.exists():
        parser.error("Choose a new .json output file; existing project data are never overwritten")
    write_text_atomic(
        args.output,
        json.dumps(result, ensure_ascii=False, indent=2) + chr(10),
    )
    print(f"Local aggregate report written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
