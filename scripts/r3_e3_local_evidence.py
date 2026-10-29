"""Local-only, read-only E3 file hash capture. Never certifies human E3."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

LABELS = ("image", "pdic", "ppp", "section", "manual", "simplified")
SCHEMA = "pc-r3-e3-local-hash-v1"
SHA40 = re.compile(r"[0-9a-fA-F]{40}\Z")
SHA64 = re.compile(r"[0-9a-fA-F]{64}\Z")


def fingerprint(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError("symlink input not allowed for E3")
    try:
        initial = path.stat()
    except FileNotFoundError:
        return {"present": False, "size": None, "sha256": None}
    if not path.is_file():
        raise ValueError("E3 artifact is not a regular file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    final = path.stat()
    fields = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
    if fields(initial) != fields(final):
        raise RuntimeError("input file changed during evidence snapshot")
    return {"present": True, "size": initial.st_size, "sha256": digest.hexdigest()}


def capture(stage: str, revision: str, paths: dict[str, Path]) -> dict:
    if stage not in ("before", "after", "reopen") or not SHA40.fullmatch(revision):
        raise ValueError("invalid stage or exact forty-digit Git revision")
    if set(paths) != set(LABELS):
        raise ValueError("six explicit artifact labels are mandatory")
    records = {name: fingerprint(paths[name]) for name in LABELS}
    if not records["image"]["present"]:
        raise ValueError("original source image is missing")
    return {"schema": SCHEMA, "kind": "LOCAL_HASH_ONLY",
            "manual_acceptance": "UNVERIFIED_REQUIRES_HUMAN",
            "stage": stage, "revision": revision.lower(),
            "utc": datetime.now(timezone.utc).isoformat(),
            "artifacts": records}


def load_report(path: Path, stage: str) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or data.get("stage") != stage:
        raise ValueError("invalid E3 report schema or stage")
    if not SHA40.fullmatch(str(data.get("revision", ""))):
        raise ValueError("invalid E3 report revision")
    rows = data.get("artifacts")
    if not isinstance(rows, dict) or set(rows) != set(LABELS):
        raise ValueError("E3 report must contain six artifacts")
    for row in rows.values():
        if not isinstance(row, dict) or type(row.get("present")) is not bool:
            raise ValueError("invalid E3 artifact record")
        if row["present"]:
            if type(row.get("size")) is not int or row["size"] < 0 or not SHA64.fullmatch(str(row.get("sha256", ""))):
                raise ValueError("invalid E3 artifact size or hash")
        elif row.get("size") is not None or row.get("sha256") is not None:
            raise ValueError("absent E3 artifact must not include a hash")
    return data


def compare(before: dict, after: dict, reopened: dict) -> dict:
    if [x["stage"] for x in (before, after, reopened)] != ["before", "after", "reopen"]:
        raise ValueError("E3 stages must be before, after, reopen")
    if len({x["revision"].lower() for x in (before, after, reopened)}) != 1:
        raise ValueError("E3 snapshots must use one exact commit revision")
    images = [x["artifacts"]["image"] for x in (before, after, reopened)]
    stable_image = bool(images[0]["present"] and images[0] == images[1] == images[2])
    rows = {}
    for name in LABELS:
        pre, post, reopen = (x["artifacts"][name] for x in (before, after, reopened))
        rows[name] = {"changed_in_operation": pre != post,
                      "stable_after_reopen": post == reopen,
                      "present_before": pre["present"],
                      "present_after": post["present"],
                      "present_reopen": reopen["present"]}
    return {"schema": SCHEMA, "kind": "COMPARISON_NOT_HUMAN_VERDICT",
            "manual_acceptance": "UNVERIFIED_REQUIRES_HUMAN",
            "revision": before["revision"].lower(),
            "image_hash_stable": stable_image,
            "sidecars_stable_after_reopen": all(row["stable_after_reopen"] for row in rows.values()),
            "artifacts": rows,
            "warning": "File hashes cannot verify source X/Y, crop pixels, IME, history or human E3."}


def create_report(path: Path, data: dict) -> None:
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    c = sub.add_parser("capture")
    c.add_argument("--stage", choices=("before", "after", "reopen"), required=True)
    c.add_argument("--revision", required=True)
    for name in LABELS:
        c.add_argument("--" + name, type=Path, required=True)
    c.add_argument("--output", type=Path, required=True)
    d = sub.add_parser("compare")
    for name in ("before", "after", "reopen"):
        d.add_argument("--" + name, type=Path, required=True)
    d.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "capture":
            result = capture(args.stage, args.revision, {name: getattr(args, name) for name in LABELS})
        else:
            result = compare(*(load_report(getattr(args, stage), stage)
                               for stage in ("before", "after", "reopen")))
        create_report(args.output, result)
        if args.mode == "compare" and (not result["image_hash_stable"] or not result["sidecars_stable_after_reopen"]):
            return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print("E3 local evidence error: " + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
