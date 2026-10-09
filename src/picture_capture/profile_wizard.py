from __future__ import annotations

"""Static composition for the GUI Project Profile wizard.

The historical base wizard remains owned by :mod:`profile_setup`. UI extensions
are composed here in the same order that the GUI bootstrap previously installed
through a module-global rebind:

base -> indentation/layout (including validation modes) -> ordinary evidence
-> parameter help.

Keeping this chain as an ordinary import removes the app's dependency on GUI
bootstrap import order without changing the individual extension builders.
"""

from .parameter_help_ui import build_profile_parameter_help_wizard
from .profile_indent_ui import build_project_profile_wizard
from .profile_ordinary_evidence_ui import build_ordinary_evidence_profile_wizard
from .profile_setup import (
    ProjectProfileWizard as _BaseProjectProfileWizard,
    _screen_work_area,
)


ProjectProfileWizard = build_profile_parameter_help_wizard(
    build_ordinary_evidence_profile_wizard(
        build_project_profile_wizard(_BaseProjectProfileWizard)
    )
)


__all__ = ["ProjectProfileWizard"]
