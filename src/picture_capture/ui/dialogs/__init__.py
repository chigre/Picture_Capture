"""Secondary Tk windows used by the Picture Capture GUI."""

from .crop_settings import CropSettingsDialog
from .ocr_conflict import OCRConflictReviewDialog
from .old_new_comparison import OldNewComparisonWindow
from .usage_guide import UsageGuideWindow

__all__ = [
    "CropSettingsDialog",
    "OCRConflictReviewDialog",
    "OldNewComparisonWindow",
    "UsageGuideWindow",
]
