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

# Phase 12F makes LayoutRows capture publication static in Layout Core. The
# compatibility entry points may remain, but they must never resume mutating
# Layout Core or the shared visualization callable.
FORBIDDEN_LAYOUT_ROWS_ASSIGNMENTS = (
    "core.understand_layout_core =",
    "shared.shared_snapshot_for_app =",
)

# Phase 12G makes Entry classification descriptors native model properties.
FORBIDDEN_ENTRY_CLASSIFICATION_ASSIGNMENTS = (
    "Entry.entry_source =",
    "Entry.entry_scale =",
    "Entry.detected_head_height =",
    "Entry.entry_scale_manual =",
)

# Phase 12H moves separator-Y and entry-crop compatibility into native
# AppSettings construction/serialization. Dynamic method/property installation
# and installer calls must not spread back into production modules.
FORBIDDEN_APP_SETTINGS_COMPAT_ASSIGNMENTS = (
    "AppSettings.__init__ =",
    "AppSettings.to_json =",
    "AppSettings.from_json =",
    "setattr(AppSettings",
)
FORBIDDEN_APP_SETTINGS_INSTALL_CALLS = (
    "install_separator_y_settings()",
    "install_entry_crop_settings()",
)
APP_SETTINGS_COMPAT_SHIMS = {
    "separator_y_settings.py",
    "entry_crop_settings.py",
}

# Phase 12J makes the public Page Design detector a static call-time forwarder.
# GUI/processing must not regain process-global ownership of that binding.
FORBIDDEN_PAGE_DESIGN_ASSIGNMENTS = (
    "dictionary_page_design.detect_entries_from_page_design =",
)

# Phase 12L moves OCR action validation to explicit action-boundary calls.
# GUI bootstrap and helper modules must not resume patching PictureCaptureApp.
FORBIDDEN_OCR_ACTION_GUARD_MUTATIONS = (
    "setattr(app_class, method_name, guarded)",
    "app_class._pc_ocr_action_guard_installed",
)
FORBIDDEN_OCR_ACTION_GUARD_INSTALL_CALLS = (
    "install_ocr_action_guard(app_module)",
)

# Phase 12M retires the redundant PictureCaptureApp tooltip terminology patch.
# Global Tk/ttk terminology normalization remains the sole product owner.
FORBIDDEN_APP_TOOLTIP_TERMINOLOGY_MUTATIONS = (
    "app_class._attach_tooltip =",
)
FORBIDDEN_APP_TOOLTIP_TERMINOLOGY_INSTALL_CALLS = (
    "install_app_tooltip_terminology(app_module)",
)

# Phase 12N moves Settings help wording/binding ownership into the static schema
# and recursive shared help binder. The post-build SettingsDialog wrapper stays retired.
FORBIDDEN_SETTINGS_HELP_RESTORE_MUTATIONS = (
    "dialog_class.__init__ = wrapped_init",
    "dialog_class._pc_settings_help_restore_installed",
)
FORBIDDEN_SETTINGS_HELP_RESTORE_INSTALL_CALLS = (
    "install_settings_help_restore(app_module)",
)

# Phase 12O moves single-line merge Settings ownership into the static crop
# schema/UI. The compatibility module must not resume mutating SettingsDialog.
FORBIDDEN_SINGLE_LINE_MERGE_MUTATIONS = (
    "dialog.__init__ =",
    "setattr(dialog, method_name, wrapped)",
    "_pc_single_line_merge_settings_installed",
    "_pc_merge_wrapped",
)
FORBIDDEN_SINGLE_LINE_MERGE_INSTALL_CALLS = (
    "install_single_line_merge_settings_ui(app_module)",
)

# Phase 12P moves unlined-export filter Settings ownership into the same static
# crop schema/UI. The compatibility helper must not resume mutating SettingsDialog.
FORBIDDEN_UNLINED_FILTER_MUTATIONS = (
    "dialog.__init__ =",
    "setattr(dialog, method_name, wrapped)",
    "_pc_unlined_filter_settings_installed",
    "_pc_unlined_filter_wrapped",
)
FORBIDDEN_UNLINED_FILTER_INSTALL_CALLS = (
    "install_unlined_export_filter_settings_ui(app_module)",
)

# Phase 12Q makes compact/right-pane Settings help native. The compatibility
# installer must not resume replacing SettingsDialog methods at runtime.
FORBIDDEN_SETTINGS_PARAMETER_HELP_MUTATIONS = (
    "dialog._add_setting_group =",
    "dialog._add_check_group =",
    "dialog._scrollable_settings_page =",
    "dialog._pc_compact_parameter_help_installed",
)
FORBIDDEN_SETTINGS_PARAMETER_HELP_INSTALL_CALLS = (
    "install_settings_parameter_help(app_module)",
)

# Phase 12R wires OCR crop preview through explicit app call sites. The
# compatibility helper must not resume patching PictureCaptureApp.
FORBIDDEN_OCR_CROP_PREVIEW_MUTATIONS = (
    "App.__init__ = init",
    "App.redraw = redraw",
    "App._draw_ocr_crop_preview =",
    "app_module._ocr_crop_preview_installed",
)
FORBIDDEN_OCR_CROP_PREVIEW_INSTALL_CALLS = (
    "install_ocr_crop_preview(app_module)",
)

# Phase 12S wires Layout visualization through explicit app call sites. The
# compatibility helper must not resume patching PictureCaptureApp methods.
FORBIDDEN_LAYOUT_VISUALIZATION_MUTATIONS = (
    "cls._section_frame =",
    "cls._build_quick_settings =",
    "cls.redraw =",
    "cls._layout_visualization_v3_installed",
)
FORBIDDEN_LAYOUT_VISUALIZATION_INSTALL_CALLS = (
    "install_layout_visualization(app_module)",
)

# Phase 12T wires Review classification through native app/ReviewWindow
# lifecycle points. The compatibility helper must not resume class/global
# mutation.
FORBIDDEN_REVIEW_CLASSIFICATION_MUTATIONS = (
    "app_module._review_line_box =",
    "ReviewWindow.__init__ =",
    "ReviewWindow._request_render_rows =",
    "ReviewWindow.set_active =",
    "ReviewWindow._build =",
    "ReviewWindow._sync_entry_classification_control =",
    "ReviewWindow._change_entry_classification =",
    "ReviewWindow._set_entry_classification_shortcut =",
    "app_module._review_entry_classification_installed",
)
FORBIDDEN_REVIEW_CLASSIFICATION_INSTALL_CALLS = (
    "install_review_entry_classification(app_module)",
)

# Phase 12U makes UI terminology source-native. The compatibility module must
# not resume mutating global Tk/ttk/StringVar constructors or GUI bootstrap.
FORBIDDEN_UI_TERMINOLOGY_MUTATIONS = (
    "cls.__init__ = wrapped_init",
    "tk.StringVar.__init__ = stringvar_init",
    "tk.StringVar.set = stringvar_set",
    "_pc_terminology_wrapped",
)
FORBIDDEN_UI_TERMINOLOGY_INSTALL_CALLS = (
    "    install_ui_terminology()",
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

    layout_rows_source = (PACKAGE_ROOT / "layout_rows_cache.py").read_text(encoding="utf-8")
    for marker in FORBIDDEN_LAYOUT_ROWS_ASSIGNMENTS:
        if marker in layout_rows_source:
            violations.append(
                f"LayoutRows process-global mutation returned: {marker}"
            )

    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        rel = path.relative_to(PACKAGE_ROOT).as_posix()
        for marker in FORBIDDEN_ENTRY_CLASSIFICATION_ASSIGNMENTS:
            if marker in source:
                violations.append(
                    f"Entry classification class mutation returned in {rel}: {marker}"
                )
        for marker in FORBIDDEN_APP_SETTINGS_COMPAT_ASSIGNMENTS:
            if marker in source:
                violations.append(
                    f"AppSettings compatibility mutation returned in {rel}: {marker}"
                )
        if rel not in APP_SETTINGS_COMPAT_SHIMS:
            for marker in FORBIDDEN_APP_SETTINGS_INSTALL_CALLS:
                if marker in source:
                    violations.append(
                        f"AppSettings compatibility installer call returned in {rel}: {marker}"
                    )
        for marker in FORBIDDEN_PAGE_DESIGN_ASSIGNMENTS:
            if marker in source:
                violations.append(
                    f"Page Design detector process-global mutation returned in {rel}: {marker}"
                )
        for marker in FORBIDDEN_OCR_ACTION_GUARD_MUTATIONS:
            if marker in source:
                violations.append(
                    f"OCR action guard class mutation returned in {rel}: {marker}"
                )
        for marker in FORBIDDEN_OCR_ACTION_GUARD_INSTALL_CALLS:
            if marker in source:
                violations.append(
                    f"OCR action guard installer call returned in {rel}: {marker}"
                )
        for marker in FORBIDDEN_APP_TOOLTIP_TERMINOLOGY_MUTATIONS:
            if marker in source:
                violations.append(
                    f"app tooltip terminology class mutation returned in {rel}: {marker}"
                )
        for marker in FORBIDDEN_APP_TOOLTIP_TERMINOLOGY_INSTALL_CALLS:
            if marker in source:
                violations.append(
                    f"app tooltip terminology installer call returned in {rel}: {marker}"
                )
        for marker in FORBIDDEN_SETTINGS_HELP_RESTORE_MUTATIONS:
            if marker in source:
                violations.append(
                    f"Settings help restore class mutation returned in {rel}: {marker}"
                )
        for marker in FORBIDDEN_SETTINGS_HELP_RESTORE_INSTALL_CALLS:
            if marker in source:
                violations.append(
                    f"Settings help restore installer call returned in {rel}: {marker}"
                )
        for marker in FORBIDDEN_SINGLE_LINE_MERGE_INSTALL_CALLS:
            if marker in source:
                violations.append(
                    f"single-line merge Settings installer call returned in {rel}: {marker}"
                )
        for marker in FORBIDDEN_UNLINED_FILTER_INSTALL_CALLS:
            if marker in source:
                violations.append(
                    f"unlined-filter Settings installer call returned in {rel}: {marker}"
                )
        for marker in FORBIDDEN_SETTINGS_PARAMETER_HELP_INSTALL_CALLS:
            if marker in source:
                violations.append(
                    f"Settings parameter-help installer call returned in {rel}: {marker}"
                )
        for marker in FORBIDDEN_OCR_CROP_PREVIEW_INSTALL_CALLS:
            if marker in source:
                violations.append(
                    f"OCR crop-preview installer call returned in {rel}: {marker}"
                )
        for marker in FORBIDDEN_LAYOUT_VISUALIZATION_INSTALL_CALLS:
            if marker in source:
                violations.append(
                    f"Layout visualization installer call returned in {rel}: {marker}"
                )
        for marker in FORBIDDEN_REVIEW_CLASSIFICATION_INSTALL_CALLS:
            if marker in source:
                violations.append(
                    f"Review classification installer call returned in {rel}: {marker}"
                )
        for marker in FORBIDDEN_UI_TERMINOLOGY_INSTALL_CALLS:
            if marker in source:
                violations.append(
                    f"UI terminology installer call returned in {rel}: {marker}"
                )

    single_line_merge_source = (
        PACKAGE_ROOT / "single_line_merge_settings.py"
    ).read_text(encoding="utf-8")
    for marker in FORBIDDEN_SINGLE_LINE_MERGE_MUTATIONS:
        if marker in single_line_merge_source:
            violations.append(
                f"single-line merge Settings mutation returned: {marker}"
            )

    unlined_filter_source = (
        PACKAGE_ROOT / "unlined_export_filter_settings.py"
    ).read_text(encoding="utf-8")
    for marker in FORBIDDEN_UNLINED_FILTER_MUTATIONS:
        if marker in unlined_filter_source:
            violations.append(
                f"unlined-filter Settings mutation returned: {marker}"
            )

    parameter_help_source = (
        PACKAGE_ROOT / "parameter_help_ui.py"
    ).read_text(encoding="utf-8")
    for marker in FORBIDDEN_SETTINGS_PARAMETER_HELP_MUTATIONS:
        if marker in parameter_help_source:
            violations.append(
                f"Settings parameter-help mutation returned: {marker}"
            )

    ocr_crop_preview_source = (
        PACKAGE_ROOT / "ocr_crop_preview_ui.py"
    ).read_text(encoding="utf-8")
    for marker in FORBIDDEN_OCR_CROP_PREVIEW_MUTATIONS:
        if marker in ocr_crop_preview_source:
            violations.append(
                f"OCR crop-preview class mutation returned: {marker}"
            )

    layout_visualization_source = (
        PACKAGE_ROOT / "layout_visualization_ui_v3.py"
    ).read_text(encoding="utf-8")
    for marker in FORBIDDEN_LAYOUT_VISUALIZATION_MUTATIONS:
        if marker in layout_visualization_source:
            violations.append(
                f"Layout visualization class mutation returned: {marker}"
            )

    review_classification_source = (
        PACKAGE_ROOT / "review_entry_classification_ui.py"
    ).read_text(encoding="utf-8")
    for marker in FORBIDDEN_REVIEW_CLASSIFICATION_MUTATIONS:
        if marker in review_classification_source:
            violations.append(
                f"Review classification mutation returned: {marker}"
            )

    ui_terminology_source = (
        PACKAGE_ROOT / "ui_terminology.py"
    ).read_text(encoding="utf-8")
    for marker in FORBIDDEN_UI_TERMINOLOGY_MUTATIONS:
        if marker in ui_terminology_source:
            violations.append(
                f"UI terminology global mutation returned: {marker}"
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
