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

    formats.write_pdic = build_write_pdic_capture(formats.write_pdic)

    from . import dictionary_page_design
    from .dictionary_page_design_refined import detect_entries_from_page_design
    from .layout_line_start_refinement import install_robust_line_starts
    from .layout_physical_indent import install_physical_indent_inference

    dictionary_page_design.detect_entries_from_page_design = (
        detect_entries_from_page_design
    )
    # First refine each row's physical start, then install the single physical-
    # indent lane/role implementation used by layout policy and Page Understanding.
    install_robust_line_starts()
    install_physical_indent_inference()

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
    install_physical_lane_summary()
    app_module.PictureCaptureApp.export_training_package = (
        export_training_package_selected_range
    )

    _PREPARED_APP_MODULE = app_module
    return app_module


def main() -> int:
    return prepare_app_module().main()
