"""Conservative Git-diff-based CI risk tiers: fail closed on unknown changes."""
from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess

FULL, FAST, DOCS = "full", "fast", "docs"

# ABI, data, image coordinate, GPU and worker lifetimes stay six-platform gates.
ALWAYS_FULL = {
    "src/picture_capture/__init__.py", "src/picture_capture/__main__.py",
    "src/picture_capture/app.py", "src/picture_capture/cli.py",
    "src/picture_capture/models.py", "src/picture_capture/formats.py",
    "src/picture_capture/project_storage.py", "src/picture_capture/page_sections.py",
    "src/picture_capture/pdic_restore.py", "src/picture_capture/processing_publish.py",
    "src/picture_capture/entry_classification.py",
    "src/picture_capture/windows_gpu.py", "src/picture_capture/runtime_environment.py",
    "src/picture_capture/ocr_channel.py", "src/picture_capture/ocr_channel_legacy.py",
    "src/picture_capture/ocr_page_resume.py", "src/picture_capture/paddle_headwords_core.py",
    "src/picture_capture/marker_refinement_parallel.py",
    "src/picture_capture/single_line_parallel.py", "src/picture_capture/unlined_line_export.py",
    "src/picture_capture/image_utils.py", "src/picture_capture/image_preprocessing.py",
    "src/picture_capture/layout_detection.py", "src/picture_capture/layout_detection_legacy.py",
    "src/picture_capture/layout_rows_cache.py", "src/picture_capture/separator_y_refinement.py",
}
ALWAYS_FULL_PREFIXES = (
    "src/picture_capture/bootstrap/", "src/picture_capture/geometry/",
    "src/picture_capture/crop/", "src/picture_capture/ocr/gpu",
    "src/picture_capture/ordinary/gpu",
)
DOC_FILES = {"README.md", "CHANGELOG.md", "CONTRIBUTING.md"}
DOC_FULL = {"docs/architecture/CHANGE_POLICY.md", "docs/architecture/CI_RISK_POLICY.md"}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def non_import_ast(source: str) -> str:
    """Preserve non-import behavior, including literals, functions and class bodies."""
    class DropImports(ast.NodeTransformer):
        def visit_Import(self, node: ast.Import):  # noqa: N802
            return None

        def visit_ImportFrom(self, node: ast.ImportFrom):  # noqa: N802
            return None

    return ast.dump(DropImports().visit(ast.parse(source)), include_attributes=False)


def content_equivalent_except_imports(before: str, after: str) -> bool:
    try:
        return non_import_ast(before) == non_import_ast(after)
    except (SyntaxError, UnicodeError, ValueError):
        return False


def changed_files(base: str, head: str = "HEAD") -> list[tuple[str, str, str]]:
    rows = git("diff", "--name-status", "-M", "--find-renames=50%", base, head).splitlines()
    changes = []
    for row in rows:
        fields = row.split("\t")
        if len(fields) == 3 and fields[0].startswith(("R", "C")):
            changes.append((fields[0][0], fields[1], fields[2]))
        elif len(fields) == 2:
            changes.append((fields[0][0], fields[1], fields[1]))
        else:
            raise ValueError(f"Unrecognized git diff row: {row!r}")
    return changes


def _is_docs(path: str) -> bool:
    return ((path.startswith("docs/") or path in DOC_FILES)
            and path.endswith((".md", ".rst", ".txt")) and path not in DOC_FULL)


def _is_test(path: str) -> bool:
    return path.startswith("tests/") and path.endswith(".py")


def _high_risk(path: str) -> bool:
    return path in ALWAYS_FULL or path.startswith(ALWAYS_FULL_PREFIXES)


def select_tier(changes, read_original, read_current):
    """Classify only mechanical import/rename diffs as fast, unknown as full."""
    if not changes:
        return FULL, ["empty/unknown diff"]
    if all(_is_docs(p) for _, old, new in changes for p in (old, new)):
        return DOCS, ["ordinary docs only"]
    reasons = []
    for kind, old, new in changes:
        if _high_risk(old) or _high_risk(new):
            return FULL, [f"critical runtime owner: {old} -> {new}"]
        if _is_docs(old) and _is_docs(new):
            continue
        if _is_test(old) and _is_test(new):
            continue
        if old == new == "scripts/architecture_guard.py" and kind == "M":
            before, after = read_original(old), read_current(new)
            if not all(line in after.splitlines() for line in before.splitlines()):
                return FULL, ["existing architecture guard content removed/changed"]
            reasons.append("guard additions")
            continue
        if (old.startswith("src/picture_capture/")
                and new.startswith("src/picture_capture/")
                and old.endswith(".py") and new.endswith(".py")
                and kind in {"M", "R"}):
            if not content_equivalent_except_imports(read_original(old), read_current(new)):
                return FULL, [f"behavioral AST change: {old} -> {new}"]
            reasons.append(f"import-only: {new}")
            continue
        return FULL, [f"unclassified status or path: {kind} {old} -> {new}"]
    return FAST, reasons or ["tests/docs only"]


def build_output(tier: str) -> dict[str, str]:
    systems = ["ubuntu-latest", "windows-latest", "macos-latest"]
    os313 = systems if tier == FULL else ["ubuntu-latest"]
    os310 = systems if tier == FULL else ["ubuntu-latest", "windows-latest"]
    return {
        "tier": tier,
        "os313": json.dumps({"include": [{"os": os} for os in os313]}, separators=(",", ":")),
        "os310": json.dumps({"include": [{"os": os} for os in os310]}, separators=(",", ":")),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    args = parser.parse_args()
    if args.full:
        tier, reasons = FULL, ["scheduled/manual/tagged full run"]
    elif not args.base:
        raise SystemExit("--base required unless --full")
    else:
        try:
            tier, reasons = select_tier(
                changed_files(args.base, args.head),
                lambda path: git("show", f"{args.base}:{path}"),
                lambda path: git("show", f"{args.head}:{path}"),
            )
        except (subprocess.CalledProcessError, UnicodeError, OSError, ValueError) as exc:
            tier, reasons = FULL, [f"fail-closed diff error: {exc}"]
    values = build_output(tier)
    print(f"CI tier = {tier}; reasons = {'; '.join(reasons)}")
    for key, value in values.items():
        print(f"{key}={value}")
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
