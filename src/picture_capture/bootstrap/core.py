from __future__ import annotations

"""Shared non-GUI composition profile for Picture Capture.

Bare ``import picture_capture`` is intentionally runtime-inert. GUI startup,
spawn workers, CLI entrypoints and application-level test/diagnostic harnesses
enter through this module when they need the composed project/detection runtime.
The remaining historical installer order stays explicit here until later phases
replace those compatibility seams with native service implementations.
"""

from dataclasses import dataclass
from types import ModuleType


@dataclass(frozen=True)
class CoreServices:
    """Process-local modules prepared for shared project/detection behavior."""

    formats: ModuleType
    processing: ModuleType


def build_core_services() -> CoreServices:
    """Install the shared runtime contract in its compatibility-safe order."""
    # Layout illustration masking is a native AppSettings field; bootstrap no
    # longer subclasses/rebinds the settings class.

    # Character-height fallback and Page Layout's detector forwarding are static,
    # so consumers no longer depend on installer ordering for that detector seam.

    # Oversized-head detection and strong row/fusion authorization are static in
    # their normal evidence/fusion modules; processing import order no longer
    # selects or mutates those callables.

    # Shared settings/classification contracts must exist before formats and
    # processing are exposed to any process profile.
    from ..separator_y_settings import install_separator_y_settings
    from ..entry_crop_settings import install_entry_crop_settings
    from ..entry_classification_fields import install_entry_classification_fields

    install_separator_y_settings()
    install_entry_crop_settings()
    install_entry_classification_fields()

    from .. import formats
    from ..entry_classification import install_pdic_classification

    install_pdic_classification(formats)

    from .. import processing as processing_module
    return CoreServices(formats=formats, processing=processing_module)


__all__ = ["CoreServices", "build_core_services"]
