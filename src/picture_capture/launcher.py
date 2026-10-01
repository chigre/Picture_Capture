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

    # Presentation terminology is installed before any Tk widgets are created.
    # Persisted setting names stay unchanged; every visible UI surface uses the
    # canonical labels “普通字/行高” and “行间空”.
    from .ui_terminology import install_ui_terminology

    install_ui_terminology()

    # 1) Capture the exact automatic PDIC result *before* processing imports
    # write_pdic into its own module namespace. Later manual saves load entries
    # from PDIC and therefore do not carry detector runtime evidence, so they do
    # not overwrite this baseline snapshot.
    from . import formats
    from .training_baseline import build_write_pdic_capture

    formats.write_pdic = build_write_pdic_capture(formats.write_pdic)

    # 2) Keep the refined page-design compatibility symbol installed for older
    # callers.  The production processing facade now owns a higher shared Page
    # Understanding layer, so this is no longer a special "ordinary drawing"
    # promotion; it is only a compatibility bridge for direct module callers.
    from . import dictionary_page_design
    from .dictionary_page_design_refined import detect_entries_from_page_design

    dictionary_page_design.detect_entries_from_page_design = (
        detect_entries_from_page_design
    )

    # profile_setup imports processing; do this only after low-level extensions
    # above have been installed. Compose page semantics first, then put all long
    # parameter explanations in the persistent right-side help area.
    from . import profile_setup
    from .parameter_help_ui import build_profile_parameter_help_wizard
    from .profile_indent_ui import build_project_profile_wizard

    profile_setup.ProjectProfileWizard = build_profile_parameter_help_wizard(
        build_project_profile_wizard(profile_setup.ProjectProfileWizard)
    )

    # 3) Enrich the existing training exporter without replacing its proven
    # image/PDIC/PPP/OCR-copying workflow.  v3 keeps the exact automatic->human
    # correction contract; a second wrapper adds the same Page Understanding
    # diagnostics that ordinary/OCR/combined drawing now share.
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

    # Import the GUI only after all function-level extensions above are in
    # place. Training export reuses the main-window page selection directly.
    from . import app as app_module
    from .layout_visualization_ui_v2 import install_layout_visualization
    from .parameter_help_ui import install_settings_parameter_help
    from .training_export_ui import export_training_package_selected_range
    from .ui_terminology import install_app_tooltip_terminology

    install_settings_parameter_help(app_module)
    install_app_tooltip_terminology(app_module)
    install_layout_visualization(app_module)
    app_module.PictureCaptureApp.export_training_package = (
        export_training_package_selected_range
    )

    _PREPARED_APP_MODULE = app_module
    return app_module


def main() -> int:
    return prepare_app_module().main()
