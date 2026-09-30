from __future__ import annotations

"""Application launcher that installs small UI compatibility extensions first."""


def main() -> int:
    # app.py imports ProjectProfileWizard into its module namespace.  Patch the
    # profile_setup export before importing app so all existing call sites use
    # the indentation-aware wizard without touching the very large app module.
    from . import profile_setup
    from .profile_indent_ui import ProjectProfileWizard

    profile_setup.ProjectProfileWizard = ProjectProfileWizard

    from .app import main as app_main

    return app_main()
