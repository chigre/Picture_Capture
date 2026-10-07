from __future__ import annotations

"""GUI composition root.

This module owns the historical GUI-specific installer chain. Shared non-GUI
runtime preparation is resolved first through ``build_core_services`` so GUI and
spawn workers converge on one explicit process foundation before their
profile-specific extensions are installed.
"""

from typing import Any


_PREPARED_APP_MODULE: Any | None = None


def prepare_gui_application() -> Any:
    """Install runtime extensions once and return the fully prepared app module."""
    global _PREPARED_APP_MODULE
    if _PREPARED_APP_MODULE is not None:
        return _PREPARED_APP_MODULE

    from .core import build_core_services

    core_services = build_core_services()

    from ..ui_terminology import install_ui_terminology

    install_ui_terminology()

    formats = core_services.formats
    from ..training_baseline import build_write_pdic_capture
    from ..entry_classification import install_pdic_classification

    # Baseline capture remains the inner compatibility writer; classification is
    # the outer persistence layer so every GUI save also updates the metadata
    # sidecar without changing the historical PDIC format.
    formats.write_pdic = build_write_pdic_capture(formats.write_pdic)
    install_pdic_classification(formats)

    # Character-height fallback is now static in layout_detection; Page Design
    # and policy imports no longer depend on a local installer ordering guard.

    # The GUI Layout overlay also needs the same physical-indent runtime before
    # app import. Ordinary detection itself prepares this runtime again
    # idempotently in every process, including spawn workers.
    from .. import dictionary_page_design
    from ..dictionary_page_design_refined import detect_entries_from_page_design
    from ..layout_line_start_refinement import install_robust_line_starts
    from ..layout_physical_indent import install_physical_indent_inference

    dictionary_page_design.detect_entries_from_page_design = (
        detect_entries_from_page_design
    )
    install_robust_line_starts()
    install_physical_indent_inference()
    # Long-band row recovery and column-drift indent remeasurement are now
    # static; only the remaining physical-indent installer needs ordering.

    # Physical LayoutRows are a persistent, semantic-free cache used by
    # post-production QA. Install after the final physical Layout runtimes so a
    # normal drawing/display pass can seed exactly the rows it actually used.
    from ..layout_rows_cache import install_layout_rows_persistence_runtime

    install_layout_rows_persistence_runtime()

    from .. import profile_setup
    from ..profile_layout_bootstrap import install_profile_layout_bootstrap
    from ..parameter_help_ui import build_profile_parameter_help_wizard
    from ..profile_indent_ui import build_project_profile_wizard
    from ..profile_ordinary_evidence_ui import build_ordinary_evidence_profile_wizard

    # Profile creation establishes the stable geometry itself, so its
    # representative-page analysis must be anchor-free and OCR-free.  The main
    # application continues to use the reliable Profile-anchored Layout Core.
    install_profile_layout_bootstrap()

    profile_setup.ProjectProfileWizard = build_profile_parameter_help_wizard(
        build_ordinary_evidence_profile_wizard(
            build_project_profile_wizard(profile_setup.ProjectProfileWizard)
        )
    )

    from .. import training_export
    from ..training_export_v3 import (
        build_export_training_page,
        build_write_training_manifest,
    )
    from ..training_export_page_understanding import (
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

    # processing.detect_entries_job is now the static top-level spawn target.
    # app.py imports that stable function by value without bootstrap mutation.

    from .. import app as app_module
    from ..layout_visualization_shared import install_shared_layout_visualization_source
    from ..review_entry_classification_ui import install_review_entry_classification
    from ..ocr_crop_preview_ui import install_ocr_crop_preview

    # The shared Layout snapshot now owns its LayoutRows capture context
    # statically before being published to the UI.
    install_shared_layout_visualization_source()
    install_review_entry_classification(app_module)
    install_ocr_crop_preview(app_module)

    from ..layout_lane_summary_extension import install_physical_lane_summary
    from ..layout_visualization_role_theme import install_layout_role_theme
    from ..layout_visualization_ui_v3 import install_layout_visualization
    from ..ocr_action_guard import install_ocr_action_guard
    from ..parameter_help_ui import install_settings_parameter_help
    from ..settings_help_restore import install_settings_help_restore
    from ..single_line_merge_settings import install_single_line_merge_settings_ui
    from ..ui_terminology import install_app_tooltip_terminology
    from ..unlined_export_filter_settings import (
        install_unlined_export_filter_settings_ui,
    )
    # Illustration-mask Settings metadata is static in the shared schema.
    install_settings_parameter_help(app_module)
    install_settings_help_restore(app_module)
    install_single_line_merge_settings_ui(app_module)
    # Filter controls belong to the same integrated crop-settings surface and
    # are installed after the per-page merge switch so they appear beneath it.
    install_unlined_export_filter_settings_ui(app_module)
    install_ocr_action_guard(app_module)
    # Unlined QA now owns its physical-row fast path statically in
    # unlined_line_export.export_unlined_page_job; no GUI-time worker mutation
    # is required.
    install_app_tooltip_terminology(app_module)
    install_layout_role_theme()
    install_layout_visualization(app_module)
    # The lane-summary wrapper now appends the prepared-indent diagnostic as
    # its final step; visible indent drawing is static in the summary module.
    install_physical_lane_summary()

    _PREPARED_APP_MODULE = app_module
    return app_module


__all__ = ["prepare_gui_application"]
