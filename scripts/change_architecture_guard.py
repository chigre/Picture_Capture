#!/usr/bin/env python3
"""Guard architecture boundaries in newly added production modules.

Existing technical debt is handled by architecture_guard.py. This gate targets
new modules so we never introduce new reverse dependencies or runtime patches.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path("src/picture_capture")


def violations_in_source(source: str, path: str) -> list[str]:
    """Return architectural violations with actionable source locations."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [f"{path}:{exc.lineno}: invalid Python: {exc.msg}"]
    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "picture_capture.app" or alias.name.startswith("picture_capture.app."):
                    errors.append(f"{path}:{node.lineno}: new module imports GUI shell")
        elif isinstance(node, ast.ImportFrom):
            if (node.level and node.module == "app") or (
                node.level == 0 and node.module == "picture_capture.app"
            ):
                errors.append(f"{path}:{node.lineno}: new module imports GUI shell")
            if node.level == 1 and node.module is None and any(a.name == "app" for a in node.names):
                errors.append(f"{path}:{node.lineno}: new module imports GUI shell")
    # The two original public facade modules have intentionally moved from
    # root .py files to same-name package __init__.py files. Their *existing*
    # assignment mirror must remain installed at import time for monkeypatch
    # compatibility. Do not allow this for any other new module or call.
    historical_facades = {
        "src/picture_capture/processing/__init__.py",
        "src/picture_capture/paddle_headwords/__init__.py",
    }
    # Only module-scope statements: nested function bodies are not import-time side effects.
    top_level = list(tree.body)
    for node in top_level:
        # Also catch simple module-level assignments of calls.
        candidates = ([node.value] if isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr))
                      and isinstance(getattr(node, "value", None), ast.Call) else [])
        for call in candidates:
            func = call.func
            if isinstance(func, ast.Name) and (
                func.id == "setattr" or func.id.startswith("install_")
            ):
                is_historical_mirror = (
                    path in historical_facades
                    and func.id == "install_core_assignment_mirror"
                    and len(call.args) == 2
                    and all(
                        isinstance(arg, ast.Name) and arg.id == expected
                        for arg, expected in zip(call.args, ("__name__", "_core"))
                    )
                    and not call.keywords
                )
                if is_historical_mirror:
                    continue
                errors.append(
                    f"{path}:{node.lineno}: module-level {func.id} call; "
                    "wire dependencies explicitly at call time"
                )
    return errors


def added_modules(base: str) -> list[Path]:
    merge_base = subprocess.run(
        ["git", "merge-base", base, "HEAD"], cwd=ROOT,
        text=True, capture_output=True, check=True,
    ).stdout.strip()
    names = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AR", merge_base, "HEAD", "--",
         PACKAGE.as_posix()],
        cwd=ROOT, text=True, capture_output=True, check=True,
    ).stdout.splitlines()
    # A renaming is conservative: validate the destination as a new module.
    return [ROOT / name for name in names
            if name.endswith(".py") and (ROOT / name).is_file()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="PR target branch or commit (default HEAD^)")
    args = parser.parse_args()
    base = args.base or "HEAD^"
    try:
        paths = added_modules(base)
    except subprocess.CalledProcessError as exc:
        print(f"Architecture change guard could not determine base {base!r}: {exc.stderr}", file=sys.stderr)
        return 2
    errors: list[str] = []
    for path in paths:
        errors.extend(violations_in_source(
            path.read_text(encoding="utf-8"),
            path.relative_to(ROOT).as_posix(),
        ))
    if errors:
        print("Architecture change guard failed:\n" + "\n".join(" - " + e for e in errors))
        return 1
    print(f"Architecture change guard passed ({len(paths)} added/renamed production modules checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
