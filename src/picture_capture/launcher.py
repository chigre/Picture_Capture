from __future__ import annotations

"""Application launcher that installs compatibility/extensions before GUI use."""

from typing import Any


_PREPARED_APP_MODULE: Any | None = None


def prepare_app_module() -> Any:
    """Install runtime extensions once and return the fully prepared app module.

    GUI smoke tests call this same function as the real launcher so failures in
    descriptor-preserving monkey patches or other launcher-only wiring are
    exercised before a release is considered healthy.
    """
    global _PREPARED_APP_MODULE
    if _PREPARED_APP_MODULE is not None:
        return _PREPARED_APP_MODULE

    from .ui_terminology import install_ui_terminology

    install_ui_terminology()

    from . import formats
    from .training_baseline import build_write_pdic_capture

    formats.write_pdic = build_write_pdic_capture(formats.write_pdic)

    from . import dictionary_page_design
    from .dictionary_page_design_refined import detect_entries_from_page_design
    from .layout_binary_finalize import install_binary_layout_finalizer
    from .layout_binary_role_sync import install_binary_line_role_sync
    from .layout_grid_inference import install_grid_line_and_indent_inference
    from .layout_line_start_refinement import install_robust_line_starts

    dictionary_page_design.detect_entries_from_page_design = (
        detect_entries_from_page_design
    )
    # Detect real rows from projection, then cluster each column by that
    # column's own physical leading-whitespace distribution.  Horizontal lane
    # inference and role assignment are independent of character/line height.
    install_grid_line_and_indent_inference()
    install_robust_line_starts()
    # Keep lane and row roles synchronized during the primary semantics pass.
    install_binary_line_role_sync()
    # Legacy layout construction can still append sparse entry modes later.
    # Normalize the final returned layout so every consumer sees the same
    # strict physical-indent binary contract: one entry lane, everything else body.
    install_binary_layout_finalizer()

    from . import profile_setup
    from .parameter_help_ui import build_profile_parameter_help_wizard
    from .profile_indent_ui import build_project_profile_wizard

    profile_setup.ProjectProfileWizard = build_profile_parameter_help_wizard(
        build_project_profile_wizard(profile_setup.ProjectProfileWizard)
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

    from . import app as app_module
    from .layout_visualization_shared import (
        install_shared_layout_visualization_source,
    )

    install_shared_layout_visualization_source()

    from .layout_lane_summary_extension import install_physical_lane_summary
    from .layout_visualization_ui_v3 import install_layout_visualization
    from .parameter_help_ui import install_settings_parameter_help
    from .training_export_ui import export_training_package_selected_range
    from .ui_terminology import install_app_tooltip_terminology

    install_settings_parameter_help(app_module)
    install_app_tooltip_terminology(app_module)
    install_layout_visualization(app_module)
    # The detailed summary module exists after install_layout_visualization();
    # append the physical lane table that drives row-role classification.
    install_physical_lane_summary()
    app_module.PictureCaptureApp.export_training_package = (
        export_training_package_selected_range
    )

    _PREPARED_APP_MODULE = app_module
    return app_module


def main() -> int:
    return prepare_app_module().main()
