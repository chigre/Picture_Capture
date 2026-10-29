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


def project_paths_for_page(page: Path) -> dict[str, Path]:
    """Resolve one root-level scanned page using the application's storage rules.

    Managed/legacy PDIC and PPP, managed vs legacy Simplified, OCR
    manual-selection and migrated SECTION read fallback are intentionally
    resolved by their production owners, not inferred by filename guesses.
    This is read-only. Project page discovery currently scans root-level
    images; nested pages require the six explicit paths instead.
    """
    page = Path(page)
    if page.is_symlink() or not page.is_file():
        raise ValueError("project page must exist as a regular source image")
    from picture_capture.persistence.project_storage import (
        ocr_cache_root, page_sections_read_path_for_image,
        pdic_path_for_image, ppp_read_path_for_image,
        simplified_review_path_for_image,
    )
    root = page.parent
    return {
        "image": page,
        "pdic": pdic_path_for_image(page),
        "ppp": ppp_read_path_for_image(page),
        "section": page_sections_read_path_for_image(page),
        "manual": ocr_cache_root(root) / f"{page.stem}_manual_selection.json",
        "simplified": simplified_review_path_for_image(page),
    }


def _reject_report_at_artifact_slot(output: Path, paths: dict[str, Path]) -> None:
    # An absent sidecar still owns its pathname. Never let a report
    # masquerade as the application's real content at that destination.
    slot = output.resolve(strict=False)
    if any(p.resolve(strict=False) == slot for p in paths.values()):
        raise ValueError("evidence output collides with an input artifact slot")


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
    cp = sub.add_parser(
        "capture-page",
        help="Resolve six slots from a project-root scanned image without guessing paths",
    )
    cp.add_argument("--page", type=Path, required=True)
    cp.add_argument("--stage", choices=("before", "after", "reopen"), required=True)
    cp.add_argument("--revision", required=True)
    cp.add_argument("--output", type=Path, required=True)
    d = sub.add_parser("compare")
    for name in ("before", "after", "reopen"):
        d.add_argument("--" + name, type=Path, required=True)
    d.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode in ("capture", "capture-page"):
            paths = (
                project_paths_for_page(args.page)
                if args.mode == "capture-page"
                else {name: getattr(args, name) for name in LABELS}
            )
            _reject_report_at_artifact_slot(args.output, paths)
            result = capture(args.stage, args.revision, paths)
        else:
            result = compare(*(load_report(getattr(args, stage), stage)
                               for stage in ("before", "after", "reopen")))
        create_report(args.output, result)
        if args.mode == "compare" and (not result["image_hash_stable"] or not result["sidecars_stable_after_reopen"]):
            return 1
    except (OSError, ValueError, RuntimeError) as exc:
        # OSError.__str__ includes the original Windows file path. E3
        # reports deliberately omit private paths; CLI error logs must
        # not become a second channel for leaking those locations.
        detail = type(exc).__name__
        if isinstance(exc, OSError) and exc.errno is not None:
            detail += f" (errno={exc.errno})"
        print(
            "E3 local evidence error: " + detail
            + "; check local input/output paths, permissions and report format",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
