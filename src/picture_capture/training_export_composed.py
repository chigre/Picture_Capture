from __future__ import annotations

"""Static current training-export composition.

``training_export`` remains the stable v2 base/compatibility implementation.
Current supervised UI export composes the v3 correction layer and shared Page
Understanding layer here, so callers no longer depend on GUI bootstrap mutating
module globals before they import the exporter.
"""

from .training_export import (
    TrainingExportCancelled,
    copy_project_context,
    export_training_page as _export_training_page_v2,
    make_training_zip,
    write_training_manifest as _write_training_manifest_v2,
)
from .training_export_page_understanding import (
    build_export_training_page_with_understanding,
)
from .training_export_v3 import (
    TRAINING_EXPORT_FORMAT_V3,
    build_export_training_page,
    build_write_training_manifest,
)


export_training_page = build_export_training_page_with_understanding(
    build_export_training_page(_export_training_page_v2)
)
write_training_manifest = build_write_training_manifest(
    _write_training_manifest_v2
)
TRAINING_EXPORT_FORMAT = TRAINING_EXPORT_FORMAT_V3


__all__ = [
    "TRAINING_EXPORT_FORMAT",
    "TrainingExportCancelled",
    "copy_project_context",
    "export_training_page",
    "make_training_zip",
    "write_training_manifest",
]
