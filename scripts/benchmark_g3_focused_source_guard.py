#!/usr/bin/env python3
"""G3 focused source-guard latency probe (synthetic or private local read-only).

Never prints source paths, words, SHA digests or raw worker exceptions.
Does not certify human Windows E3 or physical GUI end-to-end latency.
"""
from __future__ import annotations

import argparse
import json
from math import ceil
from pathlib import Path
import statistics
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from PIL import Image

from picture_capture.persistence.project_storage import (
    page_sections_read_path_for_image, pdic_path_for_image,
)
from picture_capture.proofreading.focused_crop_source_fingerprint import (
    focused_crop_source_witness,
    focused_save_source_from_crop_witness,
    focused_save_source_witness,
)

SCHEMA = "pc-g3-source-guard-benchmark-v1"


class SourceChanged(RuntimeError):
    """Image/PDIC/SECTION bytes or path identity changed during a probe."""


def _stats(values_ms: list[float]) -> dict[str, float]:
    ordered = sorted(values_ms)
    return {
        "median": round(statistics.median(ordered), 3),
        "p95": round(ordered[max(0, ceil(len(ordered) * .95) - 1)], 3),
        "max": round(ordered[-1], 3),
    }


def _assert_regular_sources(page: Path) -> bool:
    # Never follow an explicitly supplied symlink or sidecar symlink. Local
    # artifacts belong to the user's own project, not this benchmarking tool.
    if not page.is_file() or page.is_symlink():
        raise ValueError("source image is not an ordinary file")
    pdic = pdic_path_for_image(page)
    if not pdic.is_file() or pdic.is_symlink():
        raise ValueError("source PDIC is not an ordinary file")
    section = page_sections_read_path_for_image(page)
    if section.is_symlink():
        raise ValueError("source SECTION is a symlink")
    if section.exists() and not section.is_file():
        raise ValueError("source SECTION is not an ordinary file")
    return section.is_file()


def measure(
    page: Path, *, rounds: int = 5, warmups: int = 1,
    dataset: str = "local-readonly",
) -> dict:
    """Measure the actual production byte witnesses, never mutate a project.

    A crop witness reads image+PDIC+SECTION; a save witness reads only
    image+SECTION. Cross-call and end-of-trial checks reject source drift.
    Timing excludes Python/Tk painting, human editing and disk publication.
    """
    if not (1 <= rounds <= 100 and 0 <= warmups <= 20):
        raise ValueError("invalid probe repetition bounds")
    page = Path(page)
    section_present = _assert_regular_sources(page)
    size_mib = round(page.stat().st_size / 1048576, 2)
    targets = [{"page_index": 0}]
    baseline_crop = focused_crop_source_witness([page], targets)
    baseline_save = focused_save_source_from_crop_witness(baseline_crop, 0)
    if baseline_save is None:
        raise SourceChanged("unprovable source")
    crop_ms, save_ms = [], []
    for iteration in range(warmups + rounds):
        begin = perf_counter_ns()
        crop = focused_crop_source_witness([page], targets)
        elapsed_crop = (perf_counter_ns() - begin) / 1e6
        if crop != baseline_crop:
            raise SourceChanged("crop source changed")

        begin = perf_counter_ns()
        saved_source = focused_save_source_witness(page)
        elapsed_save = (perf_counter_ns() - begin) / 1e6
        if saved_source != baseline_save:
            raise SourceChanged("save source changed")

        # Verify after both measurements. This does not turn multi-file
        # observations into an OS-level atomic snapshot.
        if focused_crop_source_witness([page], targets) != baseline_crop:
            raise SourceChanged("source changed after timing")
        if iteration >= warmups:
            crop_ms.append(elapsed_crop)
            save_ms.append(elapsed_save)

    return {
        "schema": SCHEMA,
        "dataset": dataset,
        "human_acceptance": "NOT_PERFORMED",
        "rounds": rounds,
        "warmups": warmups,
        "image_size_mib": size_mib,
        "section_present": section_present,
        "crop_guard_ms": _stats(crop_ms),
        "save_guard_ms": _stats(save_ms),
        "source_unchanged": True,
    }


def _make_synthetic(root: Path, side: int) -> Path:
    page = root / "synthetic.bmp"
    Image.new("RGB", (side, side), (80, 90, 100)).save(page)
    pdic = pdic_path_for_image(page)
    pdic.parent.mkdir(parents=True, exist_ok=True)
    pdic.write_bytes(b"synthetic#1#2#0.1#0.2#synthetic#@#@\n")
    section = page_sections_read_path_for_image(page)
    section.parent.mkdir(parents=True, exist_ok=True)
    section.write_bytes(b'{"format":"synthetic-perf-only"}\n')
    return page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure G3 source-byte checks; never certify human E3."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--synthetic", action="store_true")
    source.add_argument("--image", type=Path)
    parser.add_argument("--side", type=int, default=1024,
                        help="synthetic BMP side length, 64..4096 pixels")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    args = parser.parse_args(argv)
    if (args.rounds < 1 or args.rounds > 100
            or args.warmups < 0 or args.warmups > 20
            or args.side < 64 or args.side > 4096):
        print("Invalid benchmark configuration.", file=sys.stderr)
        return 2
    try:
        if args.synthetic:
            with TemporaryDirectory(prefix="pc-g3-source-perf-") as temp:
                page = _make_synthetic(Path(temp), args.side)
                result = measure(page, rounds=args.rounds,
                                 warmups=args.warmups, dataset="synthetic")
        else:
            result = measure(args.image, rounds=args.rounds,
                             warmups=args.warmups, dataset="local-readonly")
    except Exception:
        # OSError, decoding or injected failures can carry private page paths,
        # headwords and traceback details. Only a generic terminal error is
        # appropriate; the tool must never print the raw exception.
        print("Cannot verify stable source files; no benchmark result.",
              file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
