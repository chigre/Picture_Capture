#!/usr/bin/env python3
"""Explicit offline visual-verification action; NO training/export/upload.

Review the source scan and selected on-disk proofreading action yourself.
A verification is valid only for current matching PDIC + image + OCR cache.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from picture_capture.proofreading_verification import verify_saved_action, JUDGMENTS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--pdic", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--judgment", choices=sorted(JUDGMENTS), required=True)
    parser.add_argument("--ocr-cache", type=Path)
    parser.add_argument(
        "--confirm-visual-review", action="store_true",
        help="Confirm that you personally inspected the original scanned page",
    )
    args = parser.parse_args()
    if not args.confirm_visual_review:
        parser.error("Explicit --confirm-visual-review is required")
    verified = verify_saved_action(
        journal=args.journal, pdic_file=args.pdic,
        image_file=args.image, operation_id=args.operation_id,
        judgment=args.judgment, ocr_cache=args.ocr_cache,
        explicitly_confirmed=True,
    )
    print(f"Verified local operation: {verified['operation_id']} (no model training)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
