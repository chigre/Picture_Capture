from __future__ import annotations

"""Application launcher that installs small compatibility/extensions first."""


def main() -> int:
    # 1) Capture the exact automatic PDIC result *before* processing imports
    # write_pdic into its own module namespace. Later manual saves load entries
    # from PDIC and therefore do not carry detector runtime evidence, so they do
    # not overwrite this baseline snapshot.
    from . import formats
    from .training_baseline import build_write_pdic_capture

    formats.write_pdic = build_write_pdic_capture(formats.write_pdic)

    # 2) Promote page-design refinement before processing is imported. The
    # processing facade imports this symbol by value, so installation order is
    # intentional: CJK ordinary drawing now uses multi-level indent families,
    # x(y) entry lanes and top/bottom guard bands.
    from . import dictionary_page_design
    from .dictionary_page_design_refined import (
        detect_entries_from_page_design,
        layout_diagnostics,
    )

    dictionary_page_design.detect_entries_from_page_design = (
        detect_entries_from_page_design
    )
    dictionary_page_design.layout_diagnostics = layout_diagnostics

    # profile_setup imports processing; do this only after the two low-level
    # extensions above have been installed.
    from . import profile_setup
    from .profile_indent_ui import build_project_profile_wizard

    profile_setup.ProjectProfileWizard = build_project_profile_wizard(
        profile_setup.ProjectProfileWizard
    )

    # 3) Enrich the existing training exporter without replacing its proven
    # image/PDIC/PPP/OCR-copying workflow. app.py imports these functions only
    # after this point, so the normal export button receives v3 data.
    from . import training_export
    from .training_export_v3 import (
        build_export_training_page,
        build_write_training_manifest,
    )

    training_export.export_training_page = build_export_training_page(
        training_export.export_training_page
    )
    training_export.write_training_manifest = build_write_training_manifest(
        training_export.write_training_manifest
    )
    training_export.TRAINING_EXPORT_FORMAT = "picture-capture-training-v3"

    # Import the GUI only after all function-level extensions above are in
    # place. Then replace the historical "all PDIC pages" exporter with an
    # explicit inclusive page-range exporter.
    from . import app as app_module
    from .training_export_ui import export_training_package_selected_range

    app_module.PictureCaptureApp.export_training_package = (
        export_training_package_selected_range
    )

    return app_module.main()
