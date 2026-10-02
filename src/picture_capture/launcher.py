from __future__ import annotations

"""Application launcher that installs compatibility/extensions before GUI use."""

from typing import Any


_PREPARED_APP_MODULE: Any | None = None


def prepare_app_module() -> Any:
    """Install runtime extensions once and return the fully prepared app module."""
    global _PREPARED_APP_MODULE
    if _PREPARED_APP_MODULE is not None:
        return _PREPARED_APP_MODULE

    from .ui_terminology import install_ui_terminology

    install_ui_terminology()

    from . import formats
    from .training_baseline import build_write_pdic_capture
    from .entry_classification import install_pdic_classification

    # Baseline capture remains the inner compatibility writer; classification is
    # the outer persistence layer so every GUI save also updates the metadata
    # sidecar without changing the historical PDIC format.
    formats.write_pdic = build_write_pdic_capture(formats.write_pdic)
    install_pdic_classification(formats)

    # Character-height recovery must be installed before Page Design/policy
    # modules import detect_layout_parameters by value.  Only pages explicitly
    # marked fallback=character_height are eligible for this correction.
    from .layout_character_height_runtime import (
        install_character_height_fallback_runtime,
    )

    install_character_height_fallback_runtime()

    # The GUI Layout overlay also needs the same physical-indent runtime before
    # app import. Ordinary detection itself prepares this runtime again
    # idempotently in every process, including spawn workers.
    from . import dictionary_page_design
    from .dictionary_page_design_refined import detect_entries_from_page_design
    from .layout_line_start_refinement import install_robust_line_starts
    from .layout_physical_indent import install_physical_indent_inference
    from .layout_row_recovery_runtime import install_layout_row_recovery_runtime
    from .layout_column_drift_runtime import install_layout_column_drift_runtime

    dictionary_page_design.detect_entries_from_page_design = (
        detect_entries_from_page_design
    )
    install_robust_line_starts()
    install_physical_indent_inference()
    # Dense dictionary columns can form long continuous projection bands. Keep
    # those rows recoverable before any page-specific indent/drift measurement.
    install_layout_row_recovery_runtime()
    # Keep semantic column geometry fixed while allowing analysis pixels to
    # extend left of it on slanted/curved scans. This must be ready before the
    # shared Layout Core imports policy/large-head callables by value.
    install_layout_column_drift_runtime()

    from . import profile_setup
    from .profile_layout_bootstrap import install_profile_layout_bootstrap
    from .parameter_help_ui import build_profile_parameter_help_wizard
    from .profile_indent_ui import build_project_profile_wizard
    from .profile_ordinary_evidence_ui import build_ordinary_evidence_profile_wizard

    # Profile creation establishes the stable geometry itself, so its
    # representative-page analysis must be anchor-free and OCR-free.  The main
    # application continues to use the reliable Profile-anchored Layout Core.
    install_profile_layout_bootstrap()

    profile_setup.ProjectProfileWizard = build_profile_parameter_help_wizard(
        build_ordinary_evidence_profile_wizard(
            build_project_profile_wizard(profile_setup.ProjectProfileWizard)
        )
    )

    from . import training_export
    from .training_export_v3 import (
        build_export_training_page,
        build_write_training_manifest,
    )
    from .training_export_page_understanding import (
        build_export_training_page_with_understanding,
    )

    training_export.export_training_page = build_export_training_page(
        training_export.export_training_page
    )
    training_export.export_training_page = (
        build_export_training_page_with_understanding(
            training_export.export_training_page
        )
    )
    training_export.write_training_manifest = build_write_training_manifest(
        training_export.write_training_manifest
    )
    training_export.TRAINING_EXPORT_FORMAT = "picture-capture-training-v3"

    from . import processing as processing_module
    from .entry_classification_runtime import install_processing_entry_classification
    from .spawn_detection_runtime import install_spawn_detection_runtime

    install_processing_entry_classification(processing_module)
    # app.py imports detect_entries_job by value. Replace it with the top-level,
    # spawn-pickleable worker before importing app so child processes receive the
    # same Entry classification/sidecar semantics as the GUI process.
    install_spawn_detection_runtime(processing_module)

    from . import app as app_module
    from .layout_visualization_shared import install_shared_layout_visualization_source
    from .layout_local_indent_visualization_runtime import install_local_indent_visualization
    from .layout_role_provenance_runtime import install_layout_role_provenance
    from .review_entry_classification_ui import install_review_entry_classification
    from .ocr_crop_preview_ui import install_ocr_crop_preview

    install_shared_layout_visualization_source()
    install_local_indent_visualization()
    install_layout_role_provenance()
    install_review_entry_classification(app_module)
    install_ocr_crop_preview(app_module)

    from .layout_indent_visibility_runtime import install_layout_indent_visibility
    from .layout_lane_summary_extension import install_physical_lane_summary
    from .layout_visualization_role_theme import install_layout_role_theme
    from .layout_visualization_ui_v3 import install_layout_visualization
    from .ocr_action_guard import install_ocr_action_guard
    from .ordinary_action_runtime import install_ordinary_action_runtime
    from .overlay_opacity_runtime import install_overlay_opacity_runtime
    from .illustration_fill_opacity_runtime import (
        configure_overlay_opacity_defaults,
        install_illustration_fill_opacity_runtime,
    )
    from .overlay_line_anchor_runtime import install_overlay_line_anchor_runtime
    from .parameter_help_ui import install_settings_parameter_help
    from .settings_help_restore import install_settings_help_restore
    from .training_export_ui import export_training_package_selected_range
    from .ui_terminology import install_app_tooltip_terminology

    install_settings_parameter_help(app_module)
    install_settings_help_restore(app_module)
    install_ordinary_action_runtime(app_module)
    install_ocr_action_guard(app_module)
    install_app_tooltip_terminology(app_module)
    install_layout_role_theme()
    install_layout_visualization(app_module)
    install_physical_lane_summary()
    # Install after the final Layout summary wrappers so both C1/C2 prepared
    # indent spans stay visible and the per-column block counts are reported.
    install_layout_indent_visibility()
    # Set all display-overlay defaults before the line opacity runtime creates
    # AppSettings properties. Existing settings.json values remain authoritative.
    configure_overlay_opacity_defaults()
    install_overlay_opacity_runtime(app_module)
    # Illustration fill uses a real RGBA image under the editable Canvas polygon,
    # rather than Tk's historical gray50 stipple approximation.
    install_illustration_fill_opacity_runtime(app_module)
    # Line anchoring patches the shared line renderer after opacity is installed.
    install_overlay_line_anchor_runtime(app_module)
    app_module.PictureCaptureApp.export_training_package = (
        export_training_package_selected_range
    )

    _PREPARED_APP_MODULE = app_module
    return app_module


def main() -> int:
    return prepare_app_module().main()
