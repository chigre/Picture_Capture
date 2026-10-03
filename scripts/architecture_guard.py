from __future__ import annotations

"""Fail CI only when architectural debt grows beyond the PR #161 baseline.

Phase 0 intentionally does not refactor production code.  This guard records the
known debt at the Evidence Fusion v3 baseline and makes the allowed set
monotonically decreasing: deleting/shrinking legacy structures is allowed,
adding new ones is not.
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
    "app.py": 1_080_241,
    "paddle_headwords_core.py": 378_513,
    "image_preprocessing.py": 242_626,
    "profile_setup.py": 174_009,
    "processing_core.py": 169_599,
}

# Existing runtime installers are legacy debt.  Their count may only go down.
LEGACY_RUNTIME_FILES = {
    "entry_classification_runtime.py",
    "illustration_fill_opacity_runtime.py",
    "layout_character_height_runtime.py",
    "layout_column_drift_runtime.py",
    "layout_illustration_mask_runtime.py",
    "layout_indent_visibility_runtime.py",
    "layout_local_indent_visualization_runtime.py",
    "layout_role_provenance_runtime.py",
    "layout_row_recovery_runtime.py",
    "layout_visualization_rows_cache_runtime.py",
    "ordinary_action_runtime.py",
    "ordinary_large_head_runtime.py",
    "overlay_line_anchor_runtime.py",
    "overlay_opacity_runtime.py",
    "postproduction_single_line_runtime.py",
    "spawn_detection_runtime.py",
    "spawn_layout_runtime.py",
    "unicode_nonbmp_input_runtime.py",
    "unlined_fast_path_runtime.py",
    "windows_gpu_runtime.py",
}

# Dynamic module namespace/proxy behavior currently exists only in these
# compatibility facades.  No additional production module may adopt it.
LEGACY_MODULE_PROXY_FILES = {
    "processing.py",
    "evidence_fusion.py",
    "paddle_headwords.py",
}
MODULE_PROXY_MARKERS = (
    "vars(_core).items()",
    "sys.modules[__name__].__class__",
)

# Package import currently performs these installers.  Phase 1 will move them
# behind the explicit bootstrap.  Until then, additions are forbidden.
INIT_INSTALLER_BASELINE = {
    "install_layout_illustration_mask_settings",
    "install_character_height_fallback_runtime",
    "install_live_layout_detector_binding",
    "install_ordinary_large_head_runtime",
    "install_ordinary_large_head_role_guard",
    "install_separator_y_settings",
    "install_entry_crop_settings",
    "install_entry_classification_fields",
    "install_pdic_classification",
    "install_processing_entry_classification",
    "install_spawn_layout_runtime",
    "install_layout_illustration_mask_runtime",
}
_INSTALL_CALL_RE = re.compile(r"^\s*(install_[A-Za-z0-9_]+)\(", re.MULTILINE)


def _python_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def collect_violations() -> list[str]:
    violations: list[str] = []

    oversized_now: dict[str, int] = {}
    for path in _python_files():
        size = path.stat().st_size
        if size > MAX_NORMAL_MODULE_BYTES:
            rel = path.relative_to(PACKAGE_ROOT).as_posix()
            oversized_now[rel] = size
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

    proxy_files: set[str] = set()
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in MODULE_PROXY_MARKERS):
            proxy_files.add(path.relative_to(PACKAGE_ROOT).as_posix())
    for rel in sorted(proxy_files - LEGACY_MODULE_PROXY_FILES):
        violations.append(f"new dynamic module proxy/namespace copy: {rel}")

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
    print("Architecture guard passed: no debt added beyond the PR #161 baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
