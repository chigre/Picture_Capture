from __future__ import annotations

"""Keep Page Layout bound to the live layout detector implementation.

``dictionary_page_layout_policy`` historically imports
``detect_layout_parameters`` by value. Runtime adapters (for example the
character-height fallback recovery) replace the function on the
``layout_detection`` module. If the policy module was imported before that
replacement, Page Understanding can keep calling the stale detector while the
Layout diagnostic later calls the new one. The visible symptom is an impossible
state such as ``used=39 raw=59 APPLIED`` on the same page.

This adapter replaces the policy's stored callable with a tiny live forwarder.
It intentionally resolves ``layout_detection.detect_layout_parameters`` at call
time so future detector wrappers cannot diverge between Page Understanding and
diagnostics because of import order.
"""

from typing import Any


def _live_detect_layout_parameters(image: Any, settings: Any) -> Any:
    from . import layout_detection

    return layout_detection.detect_layout_parameters(image, settings)


def install_live_layout_detector_binding() -> None:
    """Point Page Layout policy at the live detector, regardless of import order."""
    from . import dictionary_page_layout_policy as policy

    if bool(getattr(policy, "_live_layout_detector_binding_installed", False)):
        return
    policy.detect_layout_parameters = _live_detect_layout_parameters
    policy._live_layout_detector_binding_installed = True


__all__ = [
    "install_live_layout_detector_binding",
]
