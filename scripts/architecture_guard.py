from __future__ import annotations

"""Fail CI when architectural debt grows beyond the ratcheted baseline.

The guard began at the PR #161 baseline and is intentionally monotonic: once a
legacy structure is removed, it must not return. Individual debt categories are
ratcheted independently as the modular-architecture refactor progresses.
"""

from pathlib import Path
import ast
import re


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "picture_capture"

# Normal production modules should remain below this size.  The five historical
# exceptions are recorded at the exact PR #161 merge baseline; each may shrink,
# but may not grow past its baseline and no new exception may appear.
MAX_NORMAL_MODULE_BYTES = 100_000
MAX_PREPROCESS_FACADE_BYTES = 55_320
MAX_PROCESSING_CORE_FACADE_BYTES = 144_300
OVERSIZED_MODULE_BASELINE = {
    "app.py": 784_737,
    "paddle_headwords_core.py": 364_070,
    "image_preprocessing.py": 150_818,
    "profile/setup.py": 174_009,
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
    "refinement/separator_y_settings.py",
    "crop/entry_crop_settings.py",
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

    # Issue #562: Tk appearance, environment and read-only Layout UI have
    # canonical physical owners; do not restore root aliases or shims.
    for former in (
        "appearance",
        "environment_center",
        "unicode_nonbmp_input",
        "layout_visualization_ui",
        "layout_visualization_ui_v2",
    ):
        if (PACKAGE_ROOT / (former + ".py")).exists():
            violations.append(f"retired UI root owner returned: {former}.py")
        if not (PACKAGE_ROOT / "ui" / (former + ".py")).is_file():
            violations.append(f"canonical UI owner missing: ui/{former}.py")

    # Issue #562: platform-aware Tk UI display helpers are physically UI-owned.
    if (PACKAGE_ROOT / "ui_compat.py").exists():
        violations.append("retired root owner returned: ui_compat.py")
    if not (PACKAGE_ROOT / "ui/compat.py").is_file():
        violations.append("canonical owner missing: ui/compat.py")

    # Issue #562: deferred Paddle document unwarping belongs to preprocess.
    if (PACKAGE_ROOT / "document_unwarping.py").exists():
        violations.append("retired root owner returned: document_unwarping.py")
    if not (PACKAGE_ROOT / "preprocess/document_unwarping.py").is_file():
        violations.append("canonical owner missing: preprocess/document_unwarping.py")

    # Issue #562: Layout step replay has an explicit UI owner, not a root shim.
    if (PACKAGE_ROOT / "layout_step_replay_ui.py").exists():
        violations.append("retired root owner returned: layout_step_replay_ui.py")
    if not (PACKAGE_ROOT / "ui/layout_step_replay.py").is_file():
        violations.append("canonical owner missing: ui/layout_step_replay.py")

    # Issue #562: OCR crop preview keeps its read-only Tk implementation owned by UI.
    if (PACKAGE_ROOT / "ocr_crop_preview_ui.py").exists():
        violations.append("retired root owner returned: ocr_crop_preview_ui.py")
    if not (PACKAGE_ROOT / "ui/ocr_crop_preview.py").is_file():
        violations.append("canonical owner missing: ui/ocr_crop_preview.py")

    # Issue #562: Large-head GUI diagnostics have a physical UI owner.
    if (PACKAGE_ROOT / "large_head_visualization_ui.py").exists():
        violations.append("retired root owner returned: large_head_visualization_ui.py")
    if not (PACKAGE_ROOT / "ui/large_head_visualization.py").is_file():
        violations.append("canonical owner missing: ui/large_head_visualization.py")

    # Issue #562: shared adaptive denoise belongs to preprocessing owner.
    if (PACKAGE_ROOT / "adaptive_denoise.py").exists():
        violations.append("retired root owner returned: adaptive_denoise.py")
    if not (PACKAGE_ROOT / "preprocess/adaptive_denoise.py").is_file():
        violations.append("canonical owner missing: preprocess/adaptive_denoise.py")

    # Issue #562: Y-refinement LayoutRows reuse and inference policy ownership.
    for former, canonical in (("marker_refinement_layoutrows.py", "refinement/layoutrows.py"), ("inference_performance.py", "quality/inference_performance.py")):
        if (PACKAGE_ROOT / former).exists():
            violations.append(f"retired root owner returned: {former}")
        if not (PACKAGE_ROOT / canonical).is_file():
            violations.append(f"canonical owner missing: {canonical}")

    # Issue #562: independent Crop auxiliary sidecar and UI interaction owner.
    for former, canonical in (("auxiliary_lines.py", "crop/auxiliary_lines.py"), ("auxiliary_line_controller.py", "ui/auxiliary_line_controller.py")):
        if (PACKAGE_ROOT / former).exists():
            violations.append(f"retired root owner returned: {former}")
        if not (PACKAGE_ROOT / canonical).is_file():
            violations.append(f"canonical owner missing: {canonical}")

    # Issue #562: physical Crop Settings owner paths, no root compatibility shims.
    for former, canonical in (("single_line_merge_settings.py", "crop/single_line_merge_settings.py"), ("unlined_export_filter_settings.py", "crop/unlined_export_filter_settings.py")):
        if (PACKAGE_ROOT / former).exists():
            violations.append(f"retired root owner returned: {former}")
        if not (PACKAGE_ROOT / canonical).is_file():
            violations.append(f"canonical owner missing: {canonical}")

    # Issue #562: physical UI progress and line-difference bookmark owners.
    for former, canonical in (
        ("batch_progress_budget.py", "ui/batch_progress_budget.py"),
        ("line_diff_bookmarks.py", "refinement/line_diff_bookmarks.py"),
    ):
        if (PACKAGE_ROOT / former).exists():
            violations.append(f"retired root owner returned: {former}")
        if not (PACKAGE_ROOT / canonical).is_file():
            violations.append(f"canonical owner missing: {canonical}")

    # Issue #562: canonical Training ownership, no obsolete root shims.
    for former, canonical in (
        ("training_baseline.py", "training/baseline.py"),
        ("training_export_composed.py", "training/export_composed.py"),
        ("training_export_complete_dialog.py", "training/export_complete_dialog.py"),
    ):
        if (PACKAGE_ROOT / former).exists():
            violations.append(f"retired Training root owner returned: {former}")
        if not (PACKAGE_ROOT / canonical).is_file():
            violations.append(f"canonical Training owner is missing: {canonical}")


    # Issue #562: physically migrated Layout indent owner must not regress to root.
    if (PACKAGE_ROOT / "layout_indent_visibility.py").exists():
        violations.append("migrated Layout indent module returned at package root")
    if not (PACKAGE_ROOT / "layout" / "indent_visibility.py").is_file():
        violations.append("canonical Layout indent visibility owner is missing")

    for former, canonical in (
        ("layout_role_provenance.py", "layout/role_provenance.py"),
        ("layout_lane_summary_extension.py", "layout/lane_summary_extension.py"),
        ("layout_character_height.py", "layout/character_height.py"),
        ("layout_parameter_evidence.py", "layout/parameter_evidence.py"),
        ("layout_scale_experiment.py", "layout/scale_experiment.py"),
        ("layout_step_trace.py", "layout/step_trace.py"),
        ("layout_textbox_leading.py", "layout/textbox_leading.py"),
        ("layout_column_drift.py", "layout/column_drift.py"),
        ("layout_column_indent_recovery.py", "layout/column_indent_recovery.py"),
        ("layout_line_start_refinement.py", "layout/line_start_refinement.py"),
        ("layout_local_indent_visualization.py", "layout/local_indent_visualization.py"),
        ("layout_oversized_ink_continuation.py", "layout/oversized_ink_continuation.py"),
        ("layout_illustration_mask.py", "layout/illustration_mask.py"),
        ("layout_mask_source_guard.py", "layout/mask_source_guard.py"),
        ("layout_reliability.py", "layout/reliability.py"),
        ("layout_role_visual_consistency.py", "layout/role_visual_consistency.py"),
        ("layout_verified_oversized_heads.py", "layout/verified_oversized_heads.py"),
        ("layout_visualization_readability.py", "layout/visualization_readability.py"),
        ("layout_details_window.py", "layout/details_window.py"),
    ):
        if (PACKAGE_ROOT / former).exists():
            violations.append(f"migrated Layout module returned at root: {former}")
        if not (PACKAGE_ROOT / canonical).is_file():
            violations.append(f"canonical Layout module is missing: {canonical}")

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

    # #562: physically own the shared mirror in compat/ without a root shim.
    mirror_owner = PACKAGE_ROOT / "compat/facade_mirror.py"
    if (PACKAGE_ROOT / "facade_compat.py").is_file():
        violations.append("retired root facade compatibility owner returned")
    if not mirror_owner.is_file():
        violations.append("canonical facade compatibility owner missing")
    else:
        mirror_source = mirror_owner.read_text(encoding="utf-8")
        for signature in (
            "class CoreAssignmentMirrorModule(",
            "def publish_core_namespace(",
            "def install_core_assignment_mirror(",
        ):
            if signature not in mirror_source:
                violations.append(f"canonical facade compatibility implementation missing: {signature}")

    facade_compat_users_now: set[str] = set()
    for path in _python_files():
        rel = path.relative_to(PACKAGE_ROOT).as_posix()
        if rel == "compat/facade_mirror.py":
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

    evidence_source = (PACKAGE_ROOT / "ocr/evidence_fusion.py").read_text(encoding="utf-8")
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

    layout_rows_source = (PACKAGE_ROOT / "layout/rows_cache.py").read_text(encoding="utf-8")
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
        PACKAGE_ROOT / "crop/single_line_merge_settings.py"
    ).read_text(encoding="utf-8")
    for marker in FORBIDDEN_SINGLE_LINE_MERGE_MUTATIONS:
        if marker in single_line_merge_source:
            violations.append(
                f"single-line merge Settings mutation returned: {marker}"
            )

    unlined_filter_source = (
        PACKAGE_ROOT / "crop/unlined_export_filter_settings.py"
    ).read_text(encoding="utf-8")
    for marker in FORBIDDEN_UNLINED_FILTER_MUTATIONS:
        if marker in unlined_filter_source:
            violations.append(
                f"unlined-filter Settings mutation returned: {marker}"
            )

    parameter_help_source = (
        PACKAGE_ROOT / "profile/parameter_help_ui.py"
    ).read_text(encoding="utf-8")
    for marker in FORBIDDEN_SETTINGS_PARAMETER_HELP_MUTATIONS:
        if marker in parameter_help_source:
            violations.append(
                f"Settings parameter-help mutation returned: {marker}"
            )

    ocr_crop_preview_source = (
        PACKAGE_ROOT / "ui/ocr_crop_preview.py"
    ).read_text(encoding="utf-8")
    for marker in FORBIDDEN_OCR_CROP_PREVIEW_MUTATIONS:
        if marker in ocr_crop_preview_source:
            violations.append(
                f"OCR crop-preview class mutation returned: {marker}"
            )

    # #562: the active v3 diagnostic controls have exactly one physical UI owner.
    # Preserve the static Tk/no-monkeypatch scan at the moved source.
    if (PACKAGE_ROOT / "layout_visualization_ui_v3.py").is_file():
        violations.append("retired root Layout visualization v3 owner returned")
    layout_v3_owner = PACKAGE_ROOT / "ui/layout_visualization_ui_v3.py"
    if not layout_v3_owner.is_file():
        violations.append("canonical Layout visualization v3 owner missing")
        layout_visualization_source = ""
    else:
        layout_visualization_source = layout_v3_owner.read_text(encoding="utf-8")
        for signature in (
            "def draw_layout_visualization_if_enabled(",
            "def add_layout_visualization_controls(",
            "def _set_layout_exclusive_visibility(",
            "def toggle_layout_step_replay(",
        ):
            if signature not in layout_visualization_source:
                violations.append(f"Layout visualization v3 UI owner lost: {signature}")
    # #562: three real Layout analysis implementations now belong to layout/.
    # Do not re-create root shims, delete owners, or silently rename the key routines.
    for retired, owner, signature in (
        ("layout_core_understanding", "core_understanding", "def understand_layout_core("),
        ("layout_physical_indent", "physical_indent", "def projection_line_runs("),
        ("layout_detection_legacy", "detector_legacy", "def detect_layout_parameters("),
    ):
        if (PACKAGE_ROOT / (retired + ".py")).exists():
            violations.append(f"retired Layout root module returned: {retired}")
        owned = PACKAGE_ROOT / "layout" / (owner + ".py")
        if not owned.is_file():
            violations.append(f"Layout domain implementation missing: {owner}")
        elif signature not in owned.read_text(encoding="utf-8"):
            violations.append(f"Layout domain implementation missing function: {owner}")

    # Issue #562: refinement batch ownership and Windows-spawn coordinator ABI.
    for former, new_owner, signature in (
        ("marker_refinement_parallel", "parallel", "def refine_page_job("),
        ("separator_y_refinement", "separator_y", "def refine_separator_y("),
    ):
        if (PACKAGE_ROOT / (former + ".py")).exists():
            violations.append(f"retired refinement root module returned: {former}")
        canonical = PACKAGE_ROOT / "refinement" / (new_owner + ".py")
        if not canonical.is_file():
            violations.append(f"canonical refinement owner missing: {new_owner}")
        elif signature not in canonical.read_text(encoding="utf-8"):
            violations.append(f"canonical refinement routine missing: {new_owner}")
    # #562: all real line-export coordinators live together in crop/.
    for retired, owner, expected in (
        ("single_line_parallel", "single_line_parallel", "def single_line_page_job("),
        ("unlined_line_export", "unlined_line_export", "def export_unlined_page_job("),
    ):
        if (PACKAGE_ROOT / (retired + ".py")).exists():
            violations.append(f"retired root line-export coordinator returned: {retired}")
        implementation = PACKAGE_ROOT / "crop" / (owner + ".py")
        if not implementation.is_file():
            violations.append(f"canonical crop line-export owner missing: {owner}")
        elif expected not in implementation.read_text(encoding="utf-8"):
            violations.append(f"canonical line-export worker missing: {owner}")
    # #562: persistence formats, package archiver, and GUI capture are physical io/ owners.
    for former, owner, token in (
        ("formats", "formats", "def write_pdic("),
        ("picdic", "picdic", "def build_picdic_package("),
        ("gui_io", "gui_io", "def read_pdic("),
    ):
        if (PACKAGE_ROOT / (former + ".py")).exists():
            violations.append(f"retired I/O root module returned: {former}")
        target = PACKAGE_ROOT / "io" / (owner + ".py")
        if not target.is_file():
            violations.append(f"canonical I/O owner missing: {owner}")
        elif token not in target.read_text(encoding="utf-8"):
            violations.append(f"canonical I/O owner missing key routine: {owner}")
    # #562: Layout detector and fast row-cache have physical owners under layout/.
    for retired, owner, fn in (
        ("layout_detection", "detection", "def detect_layout_parameters("),
        ("layout_rows_cache", "rows_cache", "def load_layout_rows_cache("),
    ):
        if (PACKAGE_ROOT / (retired + ".py")).exists():
            violations.append(f"retired Layout root returned: {retired}")
        owned = PACKAGE_ROOT / "layout" / (owner + ".py")
        if not owned.is_file():
            violations.append(f"canonical Layout owner missing: {owner}")
        elif fn not in owned.read_text(encoding="utf-8"):
            violations.append(f"canonical Layout routine missing: {owner}")
    # Issue #562: platform runtime and Windows GPU loader have canonical owners.
    for old, owner, required in (
        ("runtime_environment", "environment", "def resolve_paddle_device("),
        ("windows_gpu", "windows_gpu", "def configure_windows_nvidia_dlls("),
    ):
        if (PACKAGE_ROOT / (old + ".py")).exists():
            violations.append(f"retired runtime root module returned: {old}")
        target = PACKAGE_ROOT / "runtime" / (owner + ".py")
        if not target.is_file():
            violations.append(f"canonical runtime owner missing: {owner}")
        elif required not in target.read_text(encoding="utf-8"):
            violations.append(f"canonical runtime routine missing: {owner}")
    # Issue #562: SECTION sidecar and project routing have canonical persistence owners.
    for old, fn in (("project_storage", "def ensure_project_storage("),
                    ("page_sections", "def write_page_sections(")):
        if (PACKAGE_ROOT / (old + ".py")).exists():
            violations.append(f"retired root persistence implementation returned: {old}")
        owned = PACKAGE_ROOT / "persistence" / (old + ".py")
        if not owned.is_file():
            violations.append(f"canonical persistence owner missing: {old}")
        elif fn not in owned.read_text(encoding="utf-8"):
            violations.append(f"canonical persistence routine missing: {old}")
    # OCR resume must fingerprint the whole package after its physical move.
    if (PACKAGE_ROOT / "ocr_page_resume.py").exists():
        violations.append("retired root OCR resume implementation returned")
    resume_owner = PACKAGE_ROOT / "ocr/page_resume.py"
    if not resume_owner.is_file():
        violations.append("canonical OCR resume owner missing")
    elif "root = Path(__file__).resolve().parents[1]" not in resume_owner.read_text(encoding="utf-8"):
        violations.append("OCR resume must fingerprint the whole package")
    root_py_count = sum(1 for item in PACKAGE_ROOT.glob("*.py") if item.is_file())
    if root_py_count > 15:
        violations.append(f"root Python module count regressed: {root_py_count} > 15")
    for marker in FORBIDDEN_LAYOUT_VISUALIZATION_MUTATIONS:
        if marker in layout_visualization_source:
            violations.append(
                f"Layout visualization class mutation returned: {marker}"
            )

    review_classification_source = (
        PACKAGE_ROOT / "proofreading/entry_classification_ui.py"
    ).read_text(encoding="utf-8")
    for marker in FORBIDDEN_REVIEW_CLASSIFICATION_MUTATIONS:
        if marker in review_classification_source:
            violations.append(
                f"Review classification mutation returned: {marker}"
            )

    ui_terminology_source = (
        PACKAGE_ROOT / "ui/terminology_compat.py"
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


    # Issue #562: physical crop/overlay ownership, never reintroduce root shims.
    migrated_crop_overlay = {
        "crop_logging": "crop/logging.py",
        "crop_plan_formatting": "crop/plan_formatting.py",
        "crop_preview_display_settings": "crop/preview_display_settings.py",
        "crop_preview_labels": "crop/preview_labels.py",
        "overlay_layout_helpers": "ui/overlay_layout_helpers.py",
        "overlay_line_anchor": "ui/overlay_line_anchor.py",
        "overlay_opacity": "ui/overlay_opacity.py",
    }
    for old_name, owner_path in migrated_crop_overlay.items():
        if (PACKAGE_ROOT / (old_name + ".py")).exists():
            violations.append(f"retired root owner returned: {old_name}.py")
        if not (PACKAGE_ROOT / owner_path).is_file():
            violations.append(f"canonical owner missing: {owner_path}")


    # Issue #562: ordinary drawing internals have canonical physical owners.
    # GPU process ownership, public processing facades and PDIC publishers stay put.
    migrated_ordinary = {
            "ordinary_cjk_large_heads": "ordinary/cjk_large_heads.py",
            "ordinary_crossing_separator": "ordinary/crossing_separator.py",
            "ordinary_final_visual_consistency": "ordinary/final_visual_consistency.py",
            "ordinary_independent_indent_rescue": "ordinary/independent_indent_rescue.py",
            "ordinary_lane_polarity": "ordinary/lane_polarity.py",
            "ordinary_layout_inspector": "ordinary/layout_inspector.py",
            "ordinary_marker_ocr_text": "ordinary/marker_ocr_text.py",
            "ordinary_oversized_head_guard": "ordinary/oversized_head_guard.py",
            "ordinary_postprocess": "ordinary/postprocess.py",
            "ordinary_secondary_recovery": "ordinary/secondary_recovery.py",
            "ordinary_symbol_evidence": "ordinary/symbol_evidence.py",
            "ordinary_unified_diagnostics": "ordinary/unified_diagnostics.py",
            "ordinary_unified_visualization": "ordinary/unified_visualization.py",
            "ordinary_vb_brightness": "ordinary/vb_brightness.py",
            "ordinary_quick_settings": "ordinary/quick_settings.py"
    }
    for old_name, owner_path in migrated_ordinary.items():
        if (PACKAGE_ROOT / (old_name + ".py")).exists():
            violations.append(f"retired ordinary root owner returned: {old_name}.py")
        if not (PACKAGE_ROOT / owner_path).is_file():
            violations.append(f"canonical ordinary owner missing: {owner_path}")

    # Issue #562: physical leaf owners, no old root shim modules.
    migrated_leaf_owners = {
        "unlined_blank_detection": "unlined/blank_detection.py",
        "unlined_physical_rows_resolver": "unlined/physical_rows_resolver.py",
        "page_thumbnail_cache": "thumbnail/cache.py",
        "page_thumbnail_tasks": "thumbnail/tasks.py",
        "generic_block_roles": "layout/generic_block_roles.py",
        "ink_safe_separator": "refinement/ink_safe_separator.py",
        "entry_crop_settings": "crop/entry_crop_settings.py",
        "separator_y_settings": "refinement/separator_y_settings.py",
    }
    for old_name, canonical in migrated_leaf_owners.items():
        if (PACKAGE_ROOT / (old_name + ".py")).exists():
            violations.append(f"retired root owner returned: {old_name}.py")
        if not (PACKAGE_ROOT / canonical).is_file():
            violations.append(f"canonical leaf owner missing: {canonical}")

    # Issue #562: preprocessing owners have canonical physical paths.
    migrated_preprocess = {
        "image_preprocessing_canvas": "preprocess/canvas.py",
        "image_preprocessing_constants": "preprocess/constants.py",
        "image_preprocessing_models": "preprocess/models.py",
        "image_preprocessing_persistence": "preprocess/persistence.py",
        "image_preprocessing_reporting": "preprocess/reporting.py",
        "image_preprocessing_storage": "preprocess/storage.py",
        "preprocess_geometry": "preprocess/geometry.py",
        "orthogonal_dewarp": "preprocess/orthogonal_dewarp.py",
        "text_line_geometry": "preprocess/text_line_geometry.py",
        "image_metadata_status": "preprocess/image_metadata_status.py",
    }
    for old_name, canonical in migrated_preprocess.items():
        if (PACKAGE_ROOT / (old_name + ".py")).exists():
            violations.append(f"retired preprocessing root owner returned: {old_name}.py")
        if not (PACKAGE_ROOT / canonical).is_file():
            violations.append(f"canonical preprocessing owner missing: {canonical}")

    # Deskew primitives/content frames have one physical owner, not root copies.
    preprocess_facade = PACKAGE_ROOT / "image_preprocessing.py"
    preprocess_source = preprocess_facade.read_text(encoding="utf-8")
    for owner, routines in {
        "deskew.py": ("_normalize_half_turn", "_weighted_median", "estimate_skew_from_polygons",
                      "_paper_fill", "deskew_image", "_rotate_point_same_canvas",
                      "_rotate_polygons_same_canvas", "_rotated_text_box", "_polygon_boxes",
                      "_expand_box_px", "_rotate_box_same_canvas"),
        "content_bounds.py": ("_smooth_1d", "_projection_content_box",
                              "_layout_content_box_from_polygons", "_projection_skew_fallback"),
    }.items():
        path = PACKAGE_ROOT / "preprocess" / owner
        if not path.is_file():
            violations.append(f"canonical preprocessing primitive owner missing: {owner}")
            continue
        source = path.read_text(encoding="utf-8")
        for routine in routines:
            if f"def {routine}(" not in source:
                violations.append(f"preprocessing routine missing from {owner}: {routine}")
            if owner == "deskew.py" or routine == "_smooth_1d":
                if f"def {routine}(" in preprocess_source:
                    violations.append(f"preprocessing primitive duplicated at root: {routine}")
    # Orthogonal acceptance and saved-transform replay have domain owners too.
    for owner, routines in {
        "orthogonal_policy.py": ("_absolute_horizontal_quality", "_separator_vertical_span",
                                 "_orthogonal_safe_gain_cap", "_choose_orthogonal_candidate",
                                 "_orthogonal_step_payload", "_orthogonal_estimate_from_step"),
        "replay.py": ("geometry_corrected_image",),
    }.items():
        path = PACKAGE_ROOT / "preprocess" / owner
        if not path.is_file():
            violations.append(f"canonical orthogonal preprocessing owner missing: {owner}")
            continue
        source = path.read_text(encoding="utf-8")
        for routine in routines:
            if f"def {routine}(" not in source:
                violations.append(f"preprocessing routine missing from {owner}: {routine}")
            if routine not in {"_choose_orthogonal_candidate", "geometry_corrected_image"}:
                if f"def {routine}(" in preprocess_source:
                    violations.append(f"orthogonal primitive duplicated at root: {routine}")
    # Preview/crop/encoding bodies belong to the rendering leaf, not the API.
    rendering_owner = PACKAGE_ROOT / "preprocess/rendering.py"
    if not rendering_owner.is_file():
        violations.append("canonical preprocessing rendering owner missing")
    else:
        rendering_tree = ast.parse(rendering_owner.read_text(encoding="utf-8"))
        owned = {node.name for node in rendering_tree.body if isinstance(node, ast.FunctionDef)}
        for routine in ("overlay_excluded_regions", "review_image", "processed_image",
                        "processed_image_with_canvas", "save_review_preview", "save_processed_page"):
            if routine not in owned:
                violations.append(f"preprocessing rendering routine missing: {routine}")
            adapter = next((node for node in ast.parse(preprocess_source).body
                            if isinstance(node, ast.FunctionDef) and node.name == routine), None)
            if adapter is None or len(adapter.body) != 1 or not isinstance(adapter.body[0], ast.Return):
                violations.append(f"preprocessing rendering API must remain a thin adapter: {routine}")
    source_evidence_owner = PACKAGE_ROOT / "preprocess/source_evidence.py"
    if not source_evidence_owner.is_file():
        violations.append("canonical source geometry evidence owner missing")
    else:
        owner_tree = ast.parse(source_evidence_owner.read_text(encoding="utf-8"))
        if not any(isinstance(node, ast.FunctionDef)
                   and node.name == "collect_source_geometry_evidence" for node in owner_tree.body):
            violations.append("source geometry evidence collection routine missing")
    analysis_adapter = next(node for node in ast.parse(preprocess_source).body
                            if isinstance(node, ast.FunctionDef) and node.name == "analyze_preprocess_page")
    if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
           and node.func.id == "estimate_skew_from_polygons" for node in ast.walk(analysis_adapter)):
        violations.append("source skew evidence must remain in preprocess/source_evidence.py")
    if not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and isinstance(node.func.value, ast.Name) and node.func.value.id == "_source_evidence"
               and node.func.attr == "collect_source_geometry_evidence" for node in ast.walk(analysis_adapter)):
        violations.append("preprocessing analysis must compose the source evidence owner")
    finalization_owner = PACKAGE_ROOT / "preprocess/finalization.py"
    if not finalization_owner.is_file():
        violations.append("canonical preprocessing finalization owner missing")
    else:
        owner_tree = ast.parse(finalization_owner.read_text(encoding="utf-8"))
        if not any(isinstance(node, ast.FunctionDef) and node.name == "finalize_preprocess_page"
                   for node in owner_tree.body):
            violations.append("preprocessing finalization routine missing")
    if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
           and node.func.id in {"_expand_box_px", "_rotated_text_box", "_projection_content_box"}
           for node in ast.walk(analysis_adapter)):
        violations.append("final crop/confidence implementation must remain in preprocess/finalization.py")
    if not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and isinstance(node.func.value, ast.Name) and node.func.value.id == "_finalization"
               and node.func.attr == "finalize_preprocess_page" for node in ast.walk(analysis_adapter)):
        violations.append("preprocessing analysis must compose the finalization owner")
    selection_owner = PACKAGE_ROOT / "preprocess/projective_selection.py"
    if not selection_owner.is_file():
        violations.append("canonical projective selection owner missing")
    else:
        owner_tree = ast.parse(selection_owner.read_text(encoding="utf-8"))
        if not any(isinstance(node, ast.FunctionDef) and node.name == "select_projective_candidate"
                   for node in owner_tree.body):
            violations.append("projective candidate selection routine missing")
    if any(isinstance(node, ast.FunctionDef) and node.name == "distortion_audit"
           for node in ast.walk(analysis_adapter)):
        violations.append("projective distortion/selection implementation must remain in its owner")
    if not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and isinstance(node.func.value, ast.Name) and node.func.value.id == "_projective_selection"
               and node.func.attr == "select_projective_candidate" for node in ast.walk(analysis_adapter)):
        violations.append("preprocessing analysis must compose the projective selection owner")
    pixel_policy_owner = PACKAGE_ROOT / "preprocess/pixel_row_policy.py"
    if not pixel_policy_owner.is_file():
        violations.append("canonical pixel row acceptance owner missing")
    else:
        owner_tree = ast.parse(pixel_policy_owner.read_text(encoding="utf-8"))
        routines = {node.name for node in owner_tree.body if isinstance(node, ast.FunctionDef)}
        if not {"assess_candidate_pixels", "reaudit_retained_pixels"} <= routines:
            violations.append("pixel row acceptance/re-audit routines missing")
    if any(isinstance(node, ast.Name) and node.id == "retained_pixel_rows"
           for node in ast.walk(analysis_adapter)):
        violations.append("retained pixel audit implementation must remain in preprocess/pixel_row_policy.py")
    orthogonal_loop_owner = PACKAGE_ROOT / "preprocess/orthogonal_pipeline.py"
    if not orthogonal_loop_owner.is_file():
        violations.append("canonical closed-loop orthogonal pipeline owner missing")
        orthogonal_loop_tree = None
    else:
        orthogonal_loop_tree = ast.parse(orthogonal_loop_owner.read_text(encoding="utf-8"))
        loop_objects = {node.name for node in orthogonal_loop_tree.body
                        if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        if not {"OrthogonalRuntime", "OrthogonalRunResult",
                "run_orthogonal_pipeline"} <= loop_objects:
            violations.append("closed-loop orthogonal owner entrypoints missing")
    if not any(isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute)
               and isinstance(node.func.value, ast.Name)
               and node.func.value.id == "_orthogonal_pipeline"
               and node.func.attr == "run_orthogonal_pipeline"
               for node in ast.walk(analysis_adapter)):
        violations.append("preprocessing facade must compose closed-loop orthogonal owner")
    if any(isinstance(node, ast.Name)
           and node.id in {"pixel_assessment", "candidate_pixel_rows", "candidate_image",
                           "baseline_pixel_rows", "pass_index"}
           for node in ast.walk(analysis_adapter)):
        violations.append("orthogonal candidate execution implementation returned to public facade")
    if orthogonal_loop_tree is not None:
        pipeline_fn = next((node for node in orthogonal_loop_tree.body
                            if isinstance(node, ast.FunctionDef)
                            and node.name == "run_orthogonal_pipeline"), None)
        if pipeline_fn is None:
            violations.append("closed-loop orthogonal function implementation missing")
        else:
            pixel_calls = {node.func.attr for node in ast.walk(pipeline_fn)
                           if isinstance(node, ast.Call)
                           and isinstance(node.func, ast.Attribute)
                           and isinstance(node.func.value, ast.Name)
                           and node.func.value.id == "_pixel_row_policy"}
            if not {"assess_candidate_pixels", "reaudit_retained_pixels"} <= pixel_calls:
                violations.append("closed-loop owner must compose canonical pixel policy twice")
            if not any(isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                       and node.target.id == "pass_index" for node in ast.walk(pipeline_fn)):
                violations.append("closed-loop owner must retain the multi-pass correction loop")
    if any(isinstance(node, ast.Call)
           and isinstance(node.func, ast.Attribute)
           and isinstance(node.func.value, ast.Name)
           and node.func.value.id == "_pixel_row_policy" for node in ast.walk(analysis_adapter)):
        violations.append("pixel acceptance or retained audit returned to public facade")
    geometry_stage_owner = PACKAGE_ROOT / "preprocess/geometry_stages.py"
    if not geometry_stage_owner.is_file():
        violations.append("canonical optional geometry stage owner missing")
    else:
        stage_tree = ast.parse(geometry_stage_owner.read_text(encoding="utf-8"))
        stage_functions = {node.name for node in stage_tree.body
                           if isinstance(node, ast.FunctionDef)}
        if not {"apply_explicit_uvdoc", "redetect_after_perspective"} <= stage_functions:
            violations.append("optional geometry stage owner routines missing")
    if any(isinstance(node, ast.Name) and node.id == "post_perspective_polygons"
           for node in ast.walk(analysis_adapter)):
        violations.append("post-perspective redetection implementation returned to analysis root")
    stage_calls = {node.func.attr for node in ast.walk(analysis_adapter)
                   if isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Attribute)
                   and isinstance(node.func.value, ast.Name)
                   and node.func.value.id == "_geometry_stages"}
    if not {"apply_explicit_uvdoc", "redetect_after_perspective"} <= stage_calls:
        violations.append("preprocessing analysis must compose explicit geometry stages")
    stage_owner = PACKAGE_ROOT / "preprocess/perspective_stages.py"
    if not stage_owner.is_file():
        violations.append("canonical manual/projective execution owner missing")
    else:
        stage_ast = ast.parse(stage_owner.read_text(encoding="utf-8"))
        routines = {node.name for node in stage_ast.body
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        if not {"PerspectiveState", "apply_manual_perspective",
                "apply_selected_perspective"} <= routines:
            violations.append("manual and selected perspective execution owners missing")
    projective_calls = {node.func.attr for node in ast.walk(analysis_adapter)
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "_perspective_stages"}
    if not {"PerspectiveState", "apply_manual_perspective",
            "apply_selected_perspective"} <= projective_calls:
        violations.append("analysis must explicitly compose projective stage diagnostics")
    if any(isinstance(node, ast.Name)
           and node.id in {"manual_estimate", "review_reasons", "diagnostic_candidate"}
           for node in ast.walk(analysis_adapter)):
        violations.append("manual/projective diagnostic implementation returned to facade")
    if _normalized_source_size(preprocess_facade) > MAX_PREPROCESS_FACADE_BYTES:
        violations.append(f"preprocessing facade regressed beyond extracted owners ({MAX_PREPROCESS_FACADE_BYTES} bytes)")

    # Issue #562: canonical REF package owns box storage/detection/OCR.
    migrated_ref = {
        "ref_boxes": "ref/boxes.py",
        "ref_box_detection": "ref/detection.py",
        "ref_box_ocr": "ref/ocr.py",
    }
    for former, current in migrated_ref.items():
        if (PACKAGE_ROOT / (former + ".py")).exists():
            violations.append(f"retired REF root module returned: {former}.py")
        if not (PACKAGE_ROOT / current).is_file():
            violations.append(f"canonical REF module missing: {current}")

    # Issue #562: enforce physical illustration detection, labels and association ownership.
    moved_illustration = {
        "illustration_detection": "illustration/detection.py",
        "illustration_labels": "illustration/labels.py",
        "illustration_batch_association": "illustration/batch_association.py",
    }
    for former, current in moved_illustration.items():
        if (PACKAGE_ROOT / (former + ".py")).exists():
            violations.append(f"retired illustration root module returned: {former}.py")
        if not (PACKAGE_ROOT / current).is_file():
            violations.append(f"canonical illustration module missing: {current}")

    # Issue #562: Project Center and recent registry are owned by project/.
    migrated_project = {
        "project_center_metadata_cache": "project/metadata_cache.py",
        "project_center_preview_cache": "project/preview_cache.py",
        "project_folder_launcher": "project/folder_launcher.py",
        "project_parameter_templates": "project/parameter_templates.py",
        "recent_project_locking": "project/recent_locking.py",
        "recent_projects": "project/recent_projects.py",
    }
    for former, canonical in migrated_project.items():
        if (PACKAGE_ROOT / (former + ".py")).exists():
            violations.append(f"retired project root owner returned: {former}.py")
        if not (PACKAGE_ROOT / canonical).is_file():
            violations.append(f"canonical project owner missing: {canonical}")

    # Issue #562: bounded proofreading domain owners, no former-root shims.
    moved_proofreading = {
        "simplified_review": "proofreading/simplified_review.py",
        "pdic_text_cleanup": "proofreading/pdic_text_cleanup.py",
        "proofreading_candidate_history": "proofreading/candidate_history.py",
        "proofreading_identity": "proofreading/identity.py",
        "proofreading_section": "proofreading/section.py",
        "proofreading_candidate_delete": "proofreading/candidate_delete.py",
        "proofreading_capture": "proofreading/capture.py",
        "proofreading_deferred_save": "proofreading/deferred_save.py",
        "proofreading_events": "proofreading/events.py",
        "proofreading_evidence": "proofreading/evidence.py",
        "proofreading_quality_export": "proofreading/quality_export.py",
        "proofreading_review_bundle": "proofreading/review_bundle.py",
        "proofreading_save_safety": "proofreading/save_safety.py",
        "proofreading_transactions": "proofreading/transactions.py",
        "proofreading_verification": "proofreading/verification.py",
        "proofreading_verify_ui": "proofreading/verify_ui.py",
        "review_crop_extension": "proofreading/crop_extension.py",
        "review_entry_classification_ui": "proofreading/entry_classification_ui.py",
        "review_main_editor_sync": "proofreading/main_editor_sync.py",
        "review_text_helpers": "proofreading/text_helpers.py",
    }
    for former, current in moved_proofreading.items():
        if (PACKAGE_ROOT / (former + ".py")).exists():
            violations.append(f"retired proofreading root module returned: {former}.py")
        if not (PACKAGE_ROOT / current).is_file():
            violations.append(f"canonical proofreading module missing: {current}")


    # Issue #562: Profile, dictionary-page design and visual marker canonical ownership.
    # The original size baseline for moved profile/setup.py remains unchanged.
    migrated_profile_design = {
        "profile_indent_ui": "profile/indent_ui.py",
        "profile_layout_bootstrap": "profile/layout_bootstrap.py",
        "profile_ordinary_evidence_ui": "profile/ordinary_evidence_ui.py",
        "profile_semantics": "profile/semantics.py",
        "profile_setup": "profile/setup.py",
        "profile_validation_modes": "profile/validation_modes.py",
        "profile_wizard": "profile/wizard.py",
        "dictionary_profile": "profile/dictionary.py",
        "parameter_help_ui": "profile/parameter_help_ui.py",
        "dictionary_page_design": "design/page_design.py",
        "dictionary_page_design_refined": "design/page_design_refined.py",
        "dictionary_page_layout_policy": "design/layout_policy.py",
        "visual_marker_templates": "visual/marker_templates.py",
        "visual_marker_ui": "visual/marker_ui.py",
        "app_settings_migrations": "profile/settings_migrations.py",
    }
    for former, canonical in migrated_profile_design.items():
        if (PACKAGE_ROOT / (former + ".py")).exists():
            violations.append(f"retired Profile/design root module returned: {former}.py")
        if not (PACKAGE_ROOT / canonical).is_file():
            violations.append(f"canonical Profile/design owner missing: {canonical}")


    # Issue #562: bounded explicit-Y refinement leaves have physical owners.
    # Keep the spawn/parent PDIC coordinator and LayoutRows cache at root
    # until their process/persistence contracts receive separate acceptance.
    moved_refinement = {
        "marker_refinement_analysis": "refinement/analysis.py",
        "marker_refinement_fixed_band": "refinement/fixed_band.py",
        "marker_refinement_guard": "refinement/guard.py",
        "marker_refinement_progress": "refinement/progress.py",
        "marker_refinement_top_edge": "refinement/top_edge.py",
    }
    for former, current in moved_refinement.items():
        if (PACKAGE_ROOT / (former + ".py")).exists():
            violations.append(f"retired refinement root module returned: {former}.py")
        if not (PACKAGE_ROOT / current).is_file():
            violations.append(f"canonical refinement owner missing: {current}")

    # Issue #562: internal OCR decision/cache owners must not return to root.
    # Core channel, Paddle/GPU process owners and OCR resume remain separate risk gates.
    migrated_ocr_leaves = {
        "ocr_action_guard": "ocr/action_guard.py",
        "ocr_boundary_detection": "ocr/boundary_detection.py",
        "ocr_final_decisions": "ocr/final_decisions.py",
        "ocr_lazy_secondary": "ocr/lazy_secondary.py",
        "ocr_pdic_preservation": "ocr/pdic_preservation.py",
        "ocr_peer_style": "ocr/peer_style.py",
        "ocr_tesseract_runner": "ocr/tesseract_runner.py",
        "ocr_text_io": "ocr/text_io.py",
        "paddle_cache_storage": "ocr/paddle_cache_storage.py",
        "paddle_raw_cache_signature": "ocr/paddle_raw_cache_signature.py",
        "tesseract_raw_cache": "ocr/tesseract_raw_cache.py",
    }
    for former, owner in migrated_ocr_leaves.items():
        if (PACKAGE_ROOT / (former + ".py")).exists():
            violations.append(f"retired OCR root module returned: {former}.py")
        if not (PACKAGE_ROOT / owner).is_file():
            violations.append(f"canonical OCR module missing: {owner}")

    # #562: selected OCR review dedup, persisted Entry conversion and quality
    # report now share one canonical import-light OCR leaf. Keep call-time public
    # patch seams and never move model/pickle types into implementation leaves.
    ocr_review_owner = PACKAGE_ROOT / "ocr/review_finalization.py"
    ocr_review_core = PACKAGE_ROOT / "paddle_headwords_core.py"
    if not ocr_review_owner.is_file():
        violations.append("canonical OCR review finalization owner missing")
    else:
        owner_tree = ast.parse(ocr_review_owner.read_text(encoding="utf-8"))
        expected = {
            "ReviewFinalizationDeps", "_review_candidate_box_height",
            "_review_candidates_same_cjk_glyph", "_review_candidate_priority",
            "_normalize_cjk_review_word", "_looks_like_multi_cjk_headword",
            "_review_candidates_same_cjk_compound", "_candidate_has_single_cjk_identity",
            "_candidate_line_height", "_boxes_same_large_cjk_region",
            "_single_cjk_duplicate_pair", "_deduplicate_selected_cjk_review_candidates",
            "_entries_from_review_candidates", "_update_project_quality_summary",
        }
        actual = {node.name for node in owner_tree.body
                  if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        if not expected <= actual:
            violations.append("complete selected OCR review finalization chain missing")
        if any(isinstance(node, ast.ImportFrom)
               and node.module == "paddle_headwords_core"
               for node in owner_tree.body):
            violations.append("OCR finalization leaf must not import OCR core at runtime")
    if ocr_review_core.is_file():
        core_tree = ast.parse(ocr_review_core.read_text(encoding="utf-8"))
        for name in ("_deduplicate_selected_cjk_review_candidates",
                     "_entries_from_review_candidates",
                     "_update_project_quality_summary"):
            wrappers = [node for node in core_tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == name]
            if len(wrappers) != 1 or not any(
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "_review_finalization"
                and node.func.attr == name for node in ast.walk(wrappers[0])
            ):
                violations.append(f"OCR public review finalization adapter not delegated: {name}")
        if _normalized_source_size(ocr_review_core) > 351_540:
            violations.append("paddle_headwords_core regressed beyond 351540-byte reviewed OCR finalization ceiling")

    # Issue #562: dictionary reference, lexical evidence and text decoding
    # own implementation leaves, without old-root compatibility shims.
    migrated_lexicon_text = {
        "cc_cedict": "lexicon/cc_cedict.py",
        "chinese_simplify": "lexicon/chinese_simplify.py",
        "collation": "lexicon/collation.py",
        "network_lookup": "lexicon/network_lookup.py",
        "latin_glued_pos_headwords": "lexicon/latin_glued_pos_headwords.py",
        "reference_index": "lexicon/reference_index.py",
        "text_encoding": "text/encoding.py",
    }
    for former, current in migrated_lexicon_text.items():
        if (PACKAGE_ROOT / (former + ".py")).exists():
            violations.append(f"retired lexicon/text root returned: {former}.py")
        if not (PACKAGE_ROOT / current).is_file():
            violations.append(f"canonical lexicon/text owner missing: {current}")

    # Issue #562: true Layout geometry/composition/diagnostic owners; no root shims.
    moved_layout_followup = {
        "boundary_placement": "layout/boundary_placement.py",
        "layout_profile_anchor": "layout/profile_anchor.py",
        "layout_composition": "layout/composition.py",
        "page_x_registration": "layout/page_x_registration.py",
        "layout_visualization_shared": "layout/visualization_shared.py",
        "layout_visualization_summary": "layout/visualization_summary.py",
    }
    for former, canonical in moved_layout_followup.items():
        if (PACKAGE_ROOT / (former + ".py")).exists():
            violations.append(f"retired Layout root module returned: {former}.py")
        if not (PACKAGE_ROOT / canonical).is_file():
            violations.append(f"canonical Layout owner missing: {canonical}")

    # Issue #562: page coordinate, list, word-map and crop utility owners.
    relocated_page_helpers = {
        "coordinate_space": "geometry/coordinate_space.py",
        "layout_transform": "geometry/layout_transform.py",
        "page_list_helpers": "project/page_list_helpers.py",
        "page_word_mapping": "proofreading/page_word_mapping.py",
        "auxiliary_crop_partition": "crop/auxiliary_partition.py",
    }
    for former, canonical in relocated_page_helpers.items():
        if (PACKAGE_ROOT / (former + ".py")).exists():
            violations.append(f"retired page helper root module returned: {former}.py")
        if not (PACKAGE_ROOT / canonical).is_file():
            violations.append(f"canonical page helper owner missing: {canonical}")

    # Issue #562 expanded evidence package ownership gate: never restore root shims.
    evidence_batch15 = {
        "ordinary_bracket_pair": "ordinary/bracket_pair.py",
        "ordinary_cpu_pool": "ordinary/cpu_pool.py",
        "ordinary_evidence_fusion": "ordinary/evidence_fusion.py",
        "ordinary_gpu_pipeline": "ordinary/gpu_pipeline.py",
        "ordinary_indent_topology": "ordinary/indent_topology.py",
        "ordinary_large_head_evidence": "ordinary/large_head_evidence.py",
        "ordinary_large_head_role_guard": "ordinary/large_head_role_guard.py",
        "ordinary_parallel": "ordinary/parallel.py",
        "ordinary_visual": "ordinary/visual.py",
        "entry_ocr_crop": "ocr/entry_crop.py",
        "entry_ocr_visual_scale": "ocr/entry_visual_scale.py",
        "page_understanding": "layout/page_understanding.py",
        "page_understanding_fusion": "layout/page_understanding_fusion.py",
        "large_head_visual_diagnostics": "ordinary/large_head_visual_diagnostics.py",
        "layout_visualization_role_theme": "layout/visualization_role_theme.py",
    }
    for former, owner in evidence_batch15.items():
        if (PACKAGE_ROOT / (former + ".py")).exists():
            violations.append(f"retired evidence root returned: {former}.py")
        if not (PACKAGE_ROOT / owner).is_file():
            violations.append(f"missing evidence physical owner: {owner}")


    # Issue #562: Entry descriptor helpers are physically owned by proofreading.
    if (PACKAGE_ROOT / "entry_classification_fields.py").exists():
        violations.append("retired Entry descriptor root owner returned")
    if not (PACKAGE_ROOT / "proofreading/entry_classification_fields.py").is_file():
        violations.append("canonical Entry descriptor owner missing")


    # Issue #562: physical OCR engines and headword-model owners; no old shims.
    moved_ocr_leaf = {
        "ocr_engines": "ocr/engines.py",
        "paddle_headword_models": "ocr/headword_models.py",
    }
    for former, canonical in moved_ocr_leaf.items():
        if (PACKAGE_ROOT / (former + ".py")).is_file():
            violations.append(f"retired OCR leaf root owner returned: {former}.py")
        if not (PACKAGE_ROOT / canonical).is_file():
            violations.append(f"canonical OCR leaf owner missing: {canonical}")


    # Issue #562: Layout detection GUI actions are owned by UI, not the root.
    if (PACKAGE_ROOT / "layout_detection_actions.py").is_file():
        violations.append("retired Layout UI actions root owner returned")
    if not (PACKAGE_ROOT / "ui/layout_detection_actions.py").is_file():
        violations.append("canonical Layout UI actions owner missing")


    # Issue #562: sampled Symbol Evidence has one canonical Layout package owner.
    if (PACKAGE_ROOT / "symbol_evidence.py").is_file():
        violations.append("retired root symbol evidence owner returned")
    if not (PACKAGE_ROOT / "layout/symbol_evidence.py").is_file():
        violations.append("canonical Layout sampled symbol evidence owner missing")


    # Issue #562: the legacy OCR-channel execution bridge has one OCR package owner.
    # Retired root compatibility copies must not reappear as thin shims.
    if (PACKAGE_ROOT / "ocr_channel_legacy.py").is_file():
        violations.append("retired root OCR-channel bridge owner returned")
    if not (PACKAGE_ROOT / "ocr/channel_legacy.py").is_file():
        violations.append("canonical OCR-channel bridge owner missing")

    # #562: complete whole-entry plan/link/export/atomic-publication workflow
    # belongs to the import-light crop owner. Keep historical model identities
    # and root public function adapters, not algorithm copies.
    crop_workflow = PACKAGE_ROOT / "crop/page_workflow.py"
    crop_core = PACKAGE_ROOT / "processing_core.py"
    if not crop_workflow.is_file():
        violations.append("canonical whole-entry crop workflow owner missing")
    else:
        owner_tree = ast.parse(crop_workflow.read_text(encoding="utf-8"))
        expected = {
            "_base_entry_crop_pieces", "build_page_crop_plan", "_stage_page_crop_plan",
            "write_page_crop_plan", "_whitefill_polygons", "_save_union_crop",
            "split_whole_entries", "CropWorkflowDeps",
        }
        actual = {node.name for node in owner_tree.body
                  if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        if not expected <= actual:
            violations.append("complete canonical page-crop workflow missing")
        if any(isinstance(node, ast.ImportFrom) and
               node.module == "processing_core" for node in owner_tree.body):
            violations.append("crop workflow must not import the processing core at runtime")
    if crop_core.is_file():
        core_tree = ast.parse(crop_core.read_text(encoding="utf-8"))
        for name in ("build_page_crop_plan", "split_whole_entries",
                     "_base_entry_crop_pieces", "write_page_crop_plan"):
            adapters = [node for node in core_tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == name]
            if len(adapters) != 1 or not any(
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "_page_workflow"
                and node.func.attr == name for node in ast.walk(adapters[0])
            ):
                violations.append(f"public core crop adapter not delegated: {name}")
        if _normalized_source_size(crop_core) > MAX_PROCESSING_CORE_FACADE_BYTES:
            violations.append(
                f"processing_core grew past extracted crop owner ({MAX_PROCESSING_CORE_FACADE_BYTES} bytes)"
            )

    # Issue #562: crop publication transaction has one physical Crop owner.
    # Keep the root path absent; its legacy tests now import the canonical owner.
    if (PACKAGE_ROOT / "processing_publish.py").is_file():
        violations.append("retired root crop publishing owner returned")
    if not (PACKAGE_ROOT / "crop/publish.py").is_file():
        violations.append("canonical Crop publishing owner missing")

    # Issue #562: the supervised OCR evidence-fusion implementation is now
    # physically owned by ocr/. Do not reintroduce a root compatibility shim.
    if (PACKAGE_ROOT / "evidence_fusion.py").is_file():
        violations.append("retired root supervised OCR fusion returned")
    if not (PACKAGE_ROOT / "ocr/evidence_fusion.py").is_file():
        violations.append("canonical supervised OCR fusion owner missing")

    # Issue #562: stable public OCR channel re-exports pure text arbitration
    # from one import-light OCR owner; never duplicate the voting algorithm.
    arb = PACKAGE_ROOT / "ocr/text_arbitration.py"
    channel = PACKAGE_ROOT / "ocr_channel.py"
    if not arb.is_file():
        violations.append("OCR text arbitration canonical owner missing")
    else:
        owner_source = arb.read_text(encoding="utf-8")
        facade_source = channel.read_text(encoding="utf-8")
        if "def choose_ocr_text(" not in owner_source or "def channel_text_key(" not in owner_source:
            violations.append("OCR arbitration implementation absent from canonical owner")
        if "def choose_ocr_text(" in facade_source or "def channel_text_key(" in facade_source:
            violations.append("OCR voting algorithm duplicated in channel facade")
        if "from .ocr.text_arbitration import channel_text_key, choose_ocr_text" not in facade_source:
            violations.append("OCR channel stopped exporting canonical text arbitration")

    # Issue #562: keep EXIF/alpha/source-space ink predicates in one
    # preprocess owner, with unchanged function-object exports from image_utils.
    pixel_owner = PACKAGE_ROOT / "preprocess/page_pixels.py"
    image_facade = PACKAGE_ROOT / "image_utils.py"
    if not pixel_owner.is_file():
        violations.append("preprocess page pixel primitives owner missing")
    else:
        owner_source = pixel_owner.read_text(encoding="utf-8")
        facade_source = image_facade.read_text(encoding="utf-8")
        for pixel_fn in ("normalize_page_rgb", "_box_sum", "_generic_analysis_ink"):
            if f"def {pixel_fn}(" not in owner_source:
                violations.append(f"page pixel owner missing {pixel_fn}")
            if f"def {pixel_fn}(" in facade_source:
                violations.append(f"duplicate page pixel implementation: {pixel_fn}")
        if "from .preprocess.page_pixels import normalize_page_rgb, _box_sum, _generic_analysis_ink" not in facade_source:
            violations.append("image_utils lost stable page pixel re-exports")

    # Issue #562: training candidate/PDIC linkage is source-space aware and
    # has one physical owner; keep its historic root import for consumers.
    gt_owner = PACKAGE_ROOT / "training/ground_truth_matching.py"
    training_entry = PACKAGE_ROOT / "training_export.py"
    if not gt_owner.is_file():
        violations.append("training ground-truth matching owner missing")
    else:
        gt_source = gt_owner.read_text(encoding="utf-8")
        entry_source = training_entry.read_text(encoding="utf-8")
        if "def _candidate_ground_truth_link(" not in gt_source:
            violations.append("canonical training matcher implementation missing")
        if "def _candidate_ground_truth_link(" in entry_source:
            violations.append("training matcher implementation duplicated at root")
        if "from .training.ground_truth_matching import _candidate_ground_truth_link" not in entry_source:
            violations.append("training legacy matcher export disconnected")

    # Issue #562: project-context snapshot and v2 manifest serialization have
    # one import-light training owner behind the historical root API.
    manifest_owner = PACKAGE_ROOT / "training/manifest_v2.py"
    legacy_export = PACKAGE_ROOT / "training_export.py"
    if not manifest_owner.is_file():
        violations.append("training v2 manifest/context canonical owner missing")
    else:
        manifest_source = manifest_owner.read_text(encoding="utf-8")
        legacy_source = legacy_export.read_text(encoding="utf-8")
        for name in ("copy_project_context", "write_training_manifest"):
            if f"def {name}(" not in manifest_source:
                violations.append(f"training v2 canonical owner missing {name}")
            if f"def {name}(" in legacy_source:
                violations.append(f"training v2 implementation duplicated at root: {name}")
        if "from .training.manifest_v2 import (" not in legacy_source:
            violations.append("legacy training exporter lost canonical manifest/context re-exports")
        if "TRAINING_EXPORT_FORMAT" not in manifest_source:
            violations.append("training v2 canonical format marker missing")

    # Issue #562: the training archive publisher has a single physical owner,
    # with the historical public module exporting the *same* class and callable.
    zip_owner = PACKAGE_ROOT / "training/zip_publish.py"
    legacy_training = PACKAGE_ROOT / "training_export.py"
    if not zip_owner.is_file():
        violations.append("canonical training ZIP publish owner missing")
    else:
        zip_source = zip_owner.read_text(encoding="utf-8")
        training_source = legacy_training.read_text(encoding="utf-8")
        if "class TrainingExportCancelled(" not in zip_source:
            violations.append("training ZIP cancellation owner missing")
        if "def make_training_zip(" not in zip_source:
            violations.append("training ZIP publisher owner missing")
        if "class TrainingExportCancelled(" in training_source:
            violations.append("duplicate root training ZIP cancellation exception")
        if "def make_training_zip(" in training_source:
            violations.append("duplicate root training ZIP publisher")
        if "from .training.zip_publish import TrainingExportCancelled, make_training_zip" not in training_source:
            violations.append("legacy training ZIP publisher aliases disconnected")
        if 'TrainingExportCancelled.__module__ = "picture_capture.training_export"' not in zip_source:
            violations.append("training ZIP exception legacy pickle identity lost")
        if 'make_training_zip.__module__ = "picture_capture.training_export"' not in zip_source:
            violations.append("training ZIP function legacy pickle identity lost")

    # Issue #562: retire two no-op installers whose product effects are now
    # statically owned by Layout policy and the Settings schema. Physical root
    # stubs must not return just to satisfy stale diagnostic import paths.
    for former, canonical, signature in (
        (
            "layout_detector_live_binding",
            "layout/detector_live_binding.py",
            "def install_live_layout_detector_binding()",
        ),
        (
            "settings_help_restore",
            "ui/settings/legacy_help_restore.py",
            "def install_settings_help_restore(",
        ),
    ):
        if (PACKAGE_ROOT / f"{former}.py").exists():
            violations.append(f"retired no-op installer returned to root: {former}.py")
        target = PACKAGE_ROOT / canonical
        if not target.is_file():
            violations.append(f"retired no-op installer domain owner missing: {canonical}")
        elif signature not in target.read_text(encoding="utf-8"):
            violations.append(f"retired no-op installer contract missing: {canonical}")

    # Issue #562: the training scope parser and retired UI text normalizer
    # are package-owned leaves. Do not reintroduce root compatibility modules
    # or hand historical GUI/selection state back to these helpers.
    for former, canonical, signature in (
        ("training_export_ui.py", "training/legacy_scope_ui.py",
         "def resolve_export_indices("),
        ("ui_terminology.py", "ui/terminology_compat.py",
         "def normalize_ui_text("),
    ):
        if (PACKAGE_ROOT / former).is_file():
            violations.append(f"retired root helper returned: {former}")
        owner = PACKAGE_ROOT / canonical
        if not owner.is_file():
            violations.append(f"missing canonical helper owner: {canonical}")
        elif signature not in owner.read_text(encoding="utf-8"):
            violations.append(f"canonical helper lost its implementation: {canonical}")

    # Issue #562: backup PDIC restoration has one physical proofreading owner.
    # Retiring the old path must not leave a forwarding stub or duplicate writer.
    backup_owner = PACKAGE_ROOT / "proofreading/pdic_restore.py"
    if (PACKAGE_ROOT / "pdic_restore.py").is_file():
        violations.append("retired root PDIC restoration implementation returned")
    if not backup_owner.is_file():
        violations.append("canonical PDIC restoration owner missing")
    else:
        backup_source = backup_owner.read_text(encoding="utf-8")
        for signature in (
            "def build_page_lookup(", "def resolve_page_token(",
            "def parse_merged_pdic_text(", "def write_pdic_atomic(",
        ):
            if signature not in backup_source:
                violations.append(f"canonical PDIC restoration function missing: {signature}")

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
