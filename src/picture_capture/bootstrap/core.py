from __future__ import annotations

"""Shared non-GUI composition profile for Picture Capture.

This module deliberately mirrors the package-wide runtime preparation that still
exists in ``picture_capture.__init__`` during the migration.  GUI and spawn
workers now enter through this explicit profile first; the legacy package-import
path remains temporarily as an idempotent compatibility fallback.  A subsequent
PR can therefore remove import-time package installation without simultaneously
inventing a new runtime order.
"""

from dataclasses import dataclass
from types import ModuleType


@dataclass(frozen=True)
class CoreServices:
    """Process-local modules prepared for shared project/detection behavior."""

    formats: ModuleType
    processing: ModuleType


def build_core_services() -> CoreServices:
    """Install the shared runtime contract in the historical package order.

    Every installer is idempotent.  Keeping the exact order here while
    ``picture_capture.__init__`` still provides the compatibility path makes this
    a characterization step rather than a behavior change.
    """
    # AppSettings must have the real dataclass field before consumers use
    # dataclasses.replace() or pickle settings into spawn workers.
    from ..layout_illustration_mask_runtime import (
        install_layout_illustration_mask_settings,
    )

    install_layout_illustration_mask_settings()

    # Must precede consumers that capture the detector callable by value.
    from ..layout_character_height_runtime import (
        install_character_height_fallback_runtime,
    )

    install_character_height_fallback_runtime()

    from ..layout_detector_live_binding import install_live_layout_detector_binding

    install_live_layout_detector_binding()

    from ..ordinary_large_head_role_guard import install_ordinary_large_head_role_guard
    from ..ordinary_large_head_runtime import install_ordinary_large_head_runtime

    install_ordinary_large_head_runtime()
    install_ordinary_large_head_role_guard()

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
    from ..entry_classification_runtime import install_processing_entry_classification
    from ..layout_illustration_mask_runtime import install_layout_illustration_mask_runtime
    from ..spawn_layout_runtime import install_spawn_layout_runtime

    install_processing_entry_classification(processing_module)
    install_spawn_layout_runtime(processing_module)
    install_layout_illustration_mask_runtime(processing_module)

    return CoreServices(formats=formats, processing=processing_module)


__all__ = ["CoreServices", "build_core_services"]
