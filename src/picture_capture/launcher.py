from __future__ import annotations

"""Application launcher that installs small UI compatibility extensions first."""


def main() -> int:
    # app.py imports ProjectProfileWizard into its module namespace. Build the
    # indentation-aware subclass only after profile_setup is fully imported so
    # low-level layout modules can consume indentation semantics without a GUI
    # circular dependency.
    from . import profile_setup
    from .profile_indent_ui import build_project_profile_wizard

    profile_setup.ProjectProfileWizard = build_project_profile_wizard(
        profile_setup.ProjectProfileWizard
    )

    from .app import main as app_main

    return app_main()
