"""Picture Capture, restored from the 2016 VB.NET project."""

__version__ = "2.14.2"

# Install neutral, shared separator-Y setting names at package import time so
# every consumer (GUI, ordinary Layout, OCR and PDIC refinement) sees the same
# canonical API. Legacy ``paddle_*`` keys remain readable through the migration
# bridge but are no longer the public/persisted names.
from .separator_y_settings import install_separator_y_settings

install_separator_y_settings()
