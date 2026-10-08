from __future__ import annotations

"""Fail CI when architectural debt grows beyond the ratcheted baseline.

The guard began at the PR #161 baseline and is intentionally monotonic: once a
legacy structure is removed, it must not return. Individual debt categories are
ratcheted independently as the modular-architecture refactor progresses.
"""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "picture_capture"

# Normal production modules should remain below this size.  The five historical
# exceptions are recorded at the exact PR #161 merge baseline; each may shrink,
# but may not grow past its baseline and no new exception may appear.
MAX_NORMAL_MODULE_BYTES = 100_000
OVERSIZED_MODULE_BASELINE = {
    "app.py": 784_737,
    "paddle_headwords_core.py": 364_070,
    "image_preprocessing.py": 150_818,
    "profile_setup.py": 174_009,
    "processing_core.py": 158_561,
}

# Existing runtime installers are legacy debt. Their count may only go down.
LEGACY_RUNTIME_FILES: set[str] = set()

# Dynamic namespace copying and module-class assignment mirroring are separate
# compatibility debts. Ratchet them independently so one can be retired without
# hiding behind the other category.
LEGACY_NAMESPACE_COPY_FILES: set[str] = set()
NAMESPACE_COPY_MARKER = "vars(_core).items()"

LEGACY_MODULE_CLASS_PROXY_FILES: set[str] = set()
MODULE_CLASS_PROXY_MARKER = "sys.modules[__name__].__class__"

# Phase 9A centralizes the retained public compatibility mechanism instead of
# duplicating dynamic namespace/proxy implementations in each facade. Phase 9C
# ratchets that boundary so no third production module can adopt the mechanism.
FACADE_COMPAT_USERS = ("processing.py", "paddle_headwords.py")
FACADE_NAMESPACE_CALL = "publish_core_namespace(globals(), _core)"
FACADE_MIRROR_CALL = "install_core_assignment_mirror(__name__, _core)"

# Phase 6B pays off the evidence-fusion import-time supervised core mutations.
# They must not reappear; supervised behavior is passed through explicit hooks.
FORBIDDEN_EVIDENCE_CORE_ASSIGNMENTS = (
    "_core._annotate_peer_typography_matches =",
    "_core.filter_headword_records =",
)

# Phase 6D removes the default processing-facade rewrite of the core left-edge
# detector. The enhanced detector is now passed explicitly on the fallback path.
FORBIDDEN_PROCESSING_CORE_ASSIGNMENTS = (
    "_core._detect_entries_left_edge =",
)

# Phase 6E removes the final default facade-to-core write. Shared separator-Y
# behavior is now selected through explicit filter/adaptive-refiner hooks.
FORBIDDEN_PADDLE_CORE_ASSIGNMENTS = (
    "_core.refine_separator_y =",
)

# Phase 1 has paid off package-import installer debt completely. Any future
# install_* call in picture_capture.__init__ is therefore a regression.
INIT_INSTALLER_BASELINE: set[str] = set()
_INSTALL_CALL_RE = re.compile(r"^\s*(install_[A-Za-z0-9_]+)\(", re.MULTILINE)


def _python_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def _normalized_source_size(path: Path) -> int:
    """Return repository-style byte size independent of checkout line endings."""
    data = path.read_bytes()
    # The baseline sizes come from Git blobs, whose Python sources use LF.
    # A Windows checkout may materialize CRLF without any source-code change.
    return len(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))


def collect_violations() -> list[str]:
    violations: list[str] = []

    for path in _python_files():
        size = _normalized_source_size(path)
        if size > MAX_NORMAL_MODULE_BYTES:
            rel = path.relative_to(PACKAGE_ROOT).as_posix()
            baseline = OVERSIZED_MODULE_BASELINE.get(rel)
            if baseline is None:
                violations.append(
                    f"new oversized production module: {rel} ({size} bytes > "
                    f"{MAX_NORMAL_MODULE_BYTES})"
                )
            elif size > baseline:
                violations.append(
                    f"legacy oversized module grew: {rel} ({size} > baseline {baseline})"
                )

    runtime_now = {
        path.name
        for path in PACKAGE_ROOT.glob("*_runtime.py")
        if path.is_file()
    }
    for name in sorted(runtime_now - LEGACY_RUNTIME_FILES):
        violations.append(f"new runtime installer module: {name}")

    namespace_copy_files: set[str] = set()
    module_class_proxy_files: set[str] = set()
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(PACKAGE_ROOT).as_posix()
        if NAMESPACE_COPY_MARKER in text:
            namespace_copy_files.add(rel)
        if MODULE_CLASS_PROXY_MARKER in text:
            module_class_proxy_files.add(rel)

    for rel in sorted(namespace_copy_files - LEGACY_NAMESPACE_COPY_FILES):
        violations.append(f"new dynamic core namespace copy: {rel}")
    for rel in sorted(module_class_proxy_files - LEGACY_MODULE_CLASS_PROXY_FILES):
        violations.append(f"new dynamic module-class proxy: {rel}")

    facade_compat_users_now: set[str] = set()
    for path in _python_files():
        rel = path.relative_to(PACKAGE_ROOT).as_posix()
        if rel == "facade_compat.py":
            continue
        source = path.read_text(encoding="utf-8")
        if FACADE_NAMESPACE_CALL in source or FACADE_MIRROR_CALL in source:
            facade_compat_users_now.add(rel)

    for rel in sorted(facade_compat_users_now - set(FACADE_COMPAT_USERS)):
        violations.append(f"new facade compatibility user: {rel}")

    for rel in FACADE_COMPAT_USERS:
        source = (PACKAGE_ROOT / rel).read_text(encoding="utf-8")
        if FACADE_NAMESPACE_CALL not in source:
            violations.append(
                f"historical facade bypasses shared namespace compatibility owner: {rel}"
            )
        if FACADE_MIRROR_CALL not in source:
            violations.append(
                f"historical facade bypasses shared assignment compatibility owner: {rel}"
            )

    evidence_source = (PACKAGE_ROOT / "evidence_fusion.py").read_text(encoding="utf-8")
    for marker in FORBIDDEN_EVIDENCE_CORE_ASSIGNMENTS:
        if marker in evidence_source:
            violations.append(
                f"evidence_fusion import-time core mutation returned: {marker}"
            )

    processing_source = (PACKAGE_ROOT / "processing.py").read_text(encoding="utf-8")
    for marker in FORBIDDEN_PROCESSING_CORE_ASSIGNMENTS:
        if marker in processing_source:
            violations.append(
                f"processing import-time core mutation returned: {marker}"
            )

    paddle_source = (PACKAGE_ROOT / "paddle_headwords.py").read_text(encoding="utf-8")
    for marker in FORBIDDEN_PADDLE_CORE_ASSIGNMENTS:
        if marker in paddle_source:
            violations.append(
                f"paddle_headwords import-time core mutation returned: {marker}"
            )

    init_path = PACKAGE_ROOT / "__init__.py"
    init_text = init_path.read_text(encoding="utf-8")
    installers_now = set(_INSTALL_CALL_RE.findall(init_text))
    for name in sorted(installers_now - INIT_INSTALLER_BASELINE):
        violations.append(f"new import-time package installer: {name}")

    return violations


def main() -> int:
    violations = collect_violations()
    if violations:
        print("Architecture guard failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print("Architecture guard passed: no debt added beyond the ratcheted baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
