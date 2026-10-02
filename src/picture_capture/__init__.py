"""Picture Capture, restored from the 2016 VB.NET project."""

__version__ = "2.14.2"

# Character-height recovery must be installed before *any* module can import
# layout_detection.detect_layout_parameters by value.  Package import itself
# later imports processing, whose page-understanding chain imports
# dictionary_page_layout_policy; installing only in launcher.py is therefore too
# late for GUI/EXE/spawn processes.  The installer is narrow and only changes
# pages explicitly marked fallback=character_height.
from .layout_character_height_runtime import install_character_height_fallback_runtime

install_character_height_fallback_runtime()

# Install neutral, shared separator-Y setting names at package import time so
# every consumer (GUI, ordinary Layout, OCR and PDIC refinement) sees the same
# canonical API. Legacy ``paddle_*`` keys remain readable through the migration
# bridge but are no longer the public/persisted names.
from .separator_y_settings import install_separator_y_settings

install_separator_y_settings()

# Crop semantics are shared by marker OCR and proofreading. Historical
# review/Paddle field names remain readable, while runtime/persistence use
# neutral regular/oversized/right-ratio terminology.
from .entry_crop_settings import install_entry_crop_settings

install_entry_crop_settings()

# Entry classification is likewise a package-wide API. PDIC stays unchanged,
# while Entry objects expose entry_source / entry_scale / detected_head_height /
# entry_scale_manual backed by the shared classification registry and sidecar.
from .entry_classification_fields import install_entry_classification_fields

install_entry_classification_fields()

# Install classification-aware PDIC IO for every consumer, not only the GUI
# launcher. CLI/scripts therefore see the same metadata persistence contract.
from . import formats as _formats
from .entry_classification import install_pdic_classification

install_pdic_classification(_formats)

# Existing-marker OCR is also package-wide rather than launcher-only. This is
# critical for ProcessPool spawn workers, which import package modules in a fresh
# interpreter and must receive the same crop/engine dispatch as the GUI process.
from . import processing as _processing
from .entry_classification_runtime import install_processing_entry_classification

install_processing_entry_classification(_processing)
