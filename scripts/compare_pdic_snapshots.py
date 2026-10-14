"""Strict, read-only PDIC baseline vs candidate comparison.

Usage: python scripts/compare_pdic_snapshots.py BASELINE_DIR CANDIDATE_DIR
Snapshot the whole PDIC tree BEFORE rerunning detection. Exit status 1 on
any missing, extra, reordered or changed record; 2 on malformed input.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _rows(path: Path) -> list[tuple[str, ...]]:
    text = path.read_text(encoding="utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    rows = []
    for n, line in enumerate(lines, 1):
        fields = tuple(line.split("#"))
        if len(fields) < 8:
            raise ValueError(f"{path}:{n}: expected >=8 fields, found {len(fields)}")
        try:
            int(fields[1]); int(fields[2])
            float(fields[3]); float(fields[4])
        except ValueError as exc:
            raise ValueError(f"{path}:{n}: invalid coordinate or percentage") from exc
        rows.append(fields)
    return rows


def compare_trees(baseline: Path, candidate: Path, *, max_examples: int = 30) -> dict:
    """Compare full serialized row fields, preserving page and row order."""
    if not baseline.is_dir() or not candidate.is_dir():
        raise ValueError("Both baseline and candidate must be directories")
    def collect(root: Path) -> dict[str, Path]:
        return {
            str(path.relative_to(root)).replace("\\", "/"): path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() == ".pdic"
        }
    left, right = collect(baseline), collect(candidate)
    examples: list[dict] = []
    changed = 0
    for name in sorted(set(left) | set(right)):
        if name not in left or name not in right:
            changed += 1
            if len(examples) < max_examples:
                examples.append({"file": name, "issue": "missing_candidate" if name not in right else "unexpected_candidate"})
            continue
        old, new = _rows(left[name]), _rows(right[name])
        if old == new:
            continue
        changed += 1
        if len(examples) < max_examples:
            mismatches = []
            for index in range(max(len(old), len(new))):
                before = old[index] if index < len(old) else None
                after = new[index] if index < len(new) else None
                if before != after:
                    mismatches.append({"row": index + 1, "baseline": before, "candidate": after})
                if len(mismatches) >= 5:
                    break
            examples.append({"file": name, "issue": "record_difference",
                             "baseline_rows": len(old), "candidate_rows": len(new),
                             "first_differences": mismatches})
    return {
        "equal": changed == 0, "baseline_files": len(left),
        "candidate_files": len(right), "changed_files": changed,
        "examples": examples,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--json", type=Path, default=None, help="Write JSON report")
    args = parser.parse_args(argv)
    try:
        report = compare_trees(args.baseline, args.candidate)
    except (OSError, ValueError) as exc:
        print(f"PDIC comparison failed: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json:
        args.json.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
