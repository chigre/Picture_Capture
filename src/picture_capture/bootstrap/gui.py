from __future__ import annotations

"""GUI composition root.

GUI dependencies are composed without mutating Page Design primitive hooks.
Shared core services are built first so GUI and spawn workers start from the
same explicit process foundation.
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

    # Product UI terminology is source-native; GUI bootstrap no longer mutates
    # Tk/ttk widget constructors or StringVar methods.

    # GUI PDIC I/O is statically composed in gui_io. Its call-time forwarding
    # preserves the core-owned classification wrappers while adding automatic
    # baseline capture without mutating formats during GUI bootstrap.

    # Character-height fallback is now static in layout_detection; Page Design
    # and policy imports no longer depend on a local installer ordering guard.

    # All GUI Layout consumers now select explicit Physical Layout composition:
    # Layout Core, full Page Understanding, Profile validation and training
    # diagnostics. Do not rebind process-global Page Design hook names here.
    # The legacy processing/spawn installer remains for compatibility until its
    # independent exit gate is proven.

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

    # The shared Layout snapshot is owned statically by layout_visualization_ui;
    # GUI bootstrap no longer rewrites that module-global seam.
    # Review classification controls/crop semantics are wired statically by app.py.
    # OCR crop-preview controls/drawing are wired statically by app.py.

    # Settings parameter groups/right-pane help are now native static
    # SettingsDialog behavior. Single-line merge and unlined-export filters
    # likewise belong to the static crop Settings schema/UI.
    # Unlined QA now owns its physical-row fast path statically in
    # unlined_line_export.export_unlined_page_job; no GUI-time worker mutation
    # is required.
    # Layout visualization controls/drawing are wired statically by app.py.
    # Layout role colors plus physical-lane/prepared-indent diagnostics are
    # statically composed by layout_visualization_summary; GUI bootstrap no
    # longer rewrites the summary formatter.

    _PREPARED_APP_MODULE = app_module
    return app_module


__all__ = ["prepare_gui_application"]
