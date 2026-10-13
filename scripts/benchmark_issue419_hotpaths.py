#!/usr/bin/env python3
"""Repeatable #419 benchmark for real scanned pages and managed project paths.

Examples:
  uv run python scripts/benchmark_issue419_hotpaths.py --image /data/scan.tif --project /data/dictionary
  uv run python scripts/benchmark_issue419_hotpaths.py --image /data/scan.tif --repeats 6 --json report.json

Without --image a *synthetic* scan is used; report labels this explicitly.
The tool measures only the selected critical functions, not end-to-end GUI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time
import tracemalloc

from PIL import Image

from picture_capture.layout_core_understanding import _image_fingerprint
from picture_capture.project_storage import (
    _parse_managed_manifest_cached,
    is_managed_project,
    manifest_path,
)


def measure(fn, repeats: int) -> dict:
    elapsed = []
    allocation = []
    for _ in range(repeats):
        tracemalloc.start()
        t0 = time.perf_counter()
        fn()
        elapsed.append((time.perf_counter() - t0) * 1000)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        allocation.append(round(peak / 1024 / 1024, 2))
    return {
        "repeats": repeats,
        "median_ms": round(statistics.median(elapsed), 2),
        "median_python_peak_mib": round(statistics.median(allocation), 2),
        "notes": "tracemalloc excludes some PIL/native heap allocations",
    }


def run(image_path: Path | None, project: Path | None, repeats: int) -> dict:
    synthetic = image_path is None
    if synthetic:
        image = Image.new("RGB", (3000, 4200), (245, 246, 242))
    else:
        with Image.open(image_path) as opened:
            image = opened.convert("RGB")
    try:
        image.load()
        # Ensure the two algorithms produce identical content fingerprint.
        digest_baseline = lambda: hashlib.blake2b(image.tobytes(), digest_size=16).digest()
        digest_new = lambda: _image_fingerprint(image)[2]
        assert digest_baseline() == digest_new(), "image fingerprint output changed"
        output = {
            "image": str(image_path) if image_path is not None else "synthetic RGB page",
            "synthetic": synthetic,
            "pixels": list(image.size),
            "mode": image.mode,
            "baseline_monolithic_hash": measure(digest_baseline, repeats),
            "bounded_fingerprint": measure(digest_new, repeats),
        }
        if project is not None:
            manifest = manifest_path(project)
            if manifest.is_file():
                def baseline():
                    json.loads(manifest.read_text(encoding="utf-8"))
                def cached():
                    is_managed_project(project)
                _parse_managed_manifest_cached.cache_clear()
                output["manifest_read_parse"] = measure(baseline, repeats * 30)
                output["manifest_validated_cache_hit"] = measure(cached, repeats * 30)
                output["manifest_cache_stats"] = str(_parse_managed_manifest_cached.cache_info())
            else:
                output["manifest"] = "not present; no manifest benchmark"
        return output
    finally:
        image.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    report = run(args.image, args.project, args.repeats)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered + "\n", encoding="utf-8")
