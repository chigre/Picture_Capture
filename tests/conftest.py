from __future__ import annotations

"""Run application tests inside the explicit non-GUI composition profile.

The package itself is intentionally import-inert.  Most tests exercise the
composed application/service behavior rather than bare library imports, so the
shared core is prepared before pytest imports individual test modules.  Tests of
package-import cleanliness use fresh subprocesses and therefore remain isolated
from this harness composition.
"""

from picture_capture.bootstrap.core import build_core_services


build_core_services()
