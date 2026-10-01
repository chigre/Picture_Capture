"""Picture Capture, restored from the 2016 VB.NET project."""

__version__ = "2.14.2"

# Install neutral, shared separator-Y setting names at package import time so
# every consumer (GUI, ordinary Layout, OCR and PDIC refinement) sees the same
# canonical API. Legacy ``paddle_*`` keys remain readable through the migration
# bridge but are no longer the public/persisted names.
from .separator_y_settings import install_separator_y_settings

install_separator_y_settings()

# Entry classification is likewise a package-wide API.  PDIC stays unchanged,
# while Entry objects expose entry_source / entry_scale / detected_head_height /
# entry_scale_manual backed by the shared classification registry and sidecar.
from .entry_classification_fields import install_entry_classification_fields

install_entry_classification_fields()
