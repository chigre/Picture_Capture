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
        PACKAGE_ROOT / "proofreading/entry_classification_ui.py"
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
