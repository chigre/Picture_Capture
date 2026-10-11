#!/usr/bin/env python3
"""Run the actual current Picture Capture detectors on complete training ZIPs.

Requires a working Picture Capture checkout / OCR environment. This runner
creates temporary read-only copies of source scans and PDIC reference data;
the original ZIPs are never changed. Unlike benchmark_training_archives.py,
this DOES regenerate detection outputs using the current checked-out code.

Example:
  python scripts/run_training_archive_full_benchmark.py \
    "葡汉10页_training_20260930_143912_015887(1).zip" \
    --modes left_edge,paddleocr,combined --output-dir /tmp/real-benchmark
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from detection_benchmark import MODES, benchmark


def prepare_project(archive: zipfile.ZipFile, directory: Path) -> None:
    manifest = json.loads(archive.read("dataset_manifest.json"))
    directory.mkdir(parents=True, exist_ok=True)
    for page_record in manifest.get("page_records", []):
        # Files from this bundle are named in annotations, not assumed to
        # be consecutive or all PNG. This avoids path traversal and respects
        # the original GT/image coordinates.
        stem = Path(str(page_record.get("page") or "")).stem
        if not stem:
            continue
        annotation_name = f"annotations/{stem}.json"
        annotation = json.loads(archive.read(annotation_name))
        image_name = str(annotation["image"]["file"])
        if not image_name.startswith("images/"):
            raise ValueError(f"Unsafe image reference: {image_name!r}")
        image_basename = Path(image_name).name
        (directory / image_basename).write_bytes(archive.read(image_name))
        pdic_name = f"artifacts/{stem}.pdic"
        (directory / f"{stem}.pdic").write_bytes(archive.read(pdic_name))
    if not any(directory.iterdir()):
        # Version 2 exports have a page_records list. Fail loudly on any
        # malformed archive rather than silently benchmarking zero pages.
        raise ValueError("No page images were extracted from the training ZIP")
    settings_name = "project_context/picture_capture_settings.json"
    (directory / "picture_capture_settings.json").write_bytes(
        archive.read(settings_name)
    )
    profile_name = "project_context/dictionary_profile.json"
    if profile_name in archive.namelist():
        (directory / "dictionary_profile.json").write_bytes(
            archive.read(profile_name)
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("training_archives", nargs="+", type=Path)
    parser.add_argument("--modes", default="left_edge,paddleocr,combined")
    parser.add_argument("--pages", default="")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force-ocr", action="store_true")
    args = parser.parse_args()
    modes = tuple(mode.strip() for mode in args.modes.split(",") if mode.strip())
    if not modes or any(mode not in MODES for mode in modes):
        parser.error("Only left_edge,paddleocr,combined are permitted")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for index, archive_path in enumerate(args.training_archives, 1):
        with zipfile.ZipFile(archive_path) as archive:
            if "dataset_manifest.json" not in archive.namelist():
                parser.error(f"Not a labelled training ZIP: {archive_path}")
            with TemporaryDirectory(prefix="pc-real-scans-") as tmp:
                project = Path(tmp) / f"training_{index}"
                prepare_project(archive, project)
                result = benchmark(
                    project, modes, args.pages, args.force_ocr,
                )
        result["original_training_zip"] = archive_path.name
        result["uses_original_gt"] = True
        result["test_kind"] = "actual_detection_regenerated"
        output = args.output_dir / f"regenerated_{index:02d}.json"
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"{archive_path.name}: {output}")
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
