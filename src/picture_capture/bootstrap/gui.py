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

    # GUI PDIC I/O is statically composed in gui_io. Its call-time forwarding
    # preserves the core-owned classification wrappers while adding automatic
    # baseline capture without mutating formats during GUI bootstrap.

    # Character-height fallback is now static in layout_detection; Page Design
    # and policy imports no longer depend on a local installer ordering guard.

    # The GUI Layout overlay also needs the same physical-indent runtime before
    # app import. Ordinary detection itself prepares this runtime again
    # idempotently in every process, including spawn workers. The public Page
    # Design detector forwards to the refined implementation statically.
    from ..layout_line_start_refinement import install_robust_line_starts
    from ..layout_physical_indent import install_physical_indent_inference

    install_robust_line_starts()
    install_physical_indent_inference()
    # Long-band row recovery and column-drift indent remeasurement are now
    # static; only the remaining physical-indent installer needs ordering.

    # Physical LayoutRows capture is now published statically by Layout Core
    # whenever an explicit capture_layout_rows(...) context is active. GUI
    # bootstrap no longer wraps understand_layout_core for this side effect.

    # Project Profile UI extensions are composed statically in
    # profile_wizard. app.py imports that finished class directly, so
    # GUI bootstrap no longer mutates profile_setup.ProjectProfileWizard or
    # controls the wizard's import order.

    # Current training export is composed statically in training_export_composed:
    # v2 base -> v3 corrections -> shared Page Understanding. GUI startup no
    # longer mutates training_export globals or controls exporter import order.

    # processing.detect_entries_job is now the static top-level spawn target.
    # app.py imports that stable function by value without bootstrap mutation.

    from .. import app as app_module
    from ..review_entry_classification_ui import install_review_entry_classification
    from ..ocr_crop_preview_ui import install_ocr_crop_preview

    # The shared Layout snapshot is owned statically by layout_visualization_ui;
    # GUI bootstrap no longer rewrites that module-global seam.
    install_review_entry_classification(app_module)
    install_ocr_crop_preview(app_module)

    from ..layout_visualization_ui_v3 import install_layout_visualization
    from ..parameter_help_ui import install_settings_parameter_help
    from ..single_line_merge_settings import install_single_line_merge_settings_ui
    from ..unlined_export_filter_settings import (
        install_unlined_export_filter_settings_ui,
    )
    # Illustration-mask Settings metadata is static in the shared schema.
    install_settings_parameter_help(app_module)
    install_single_line_merge_settings_ui(app_module)
    # Filter controls belong to the same integrated crop-settings surface and
    # are installed after the per-page merge switch so they appear beneath it.
    install_unlined_export_filter_settings_ui(app_module)
    # Unlined QA now owns its physical-row fast path statically in
    # unlined_line_export.export_unlined_page_job; no GUI-time worker mutation
    # is required.
    install_layout_visualization(app_module)
    # Layout role colors plus physical-lane/prepared-indent diagnostics are
    # statically composed by layout_visualization_summary; GUI bootstrap no
    # longer rewrites the summary formatter.

    _PREPARED_APP_MODULE = app_module
    return app_module


__all__ = ["prepare_gui_application"]
