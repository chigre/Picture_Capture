"""Secondary Tk windows used by the Picture Capture GUI."""

from .ocr_conflict import OCRConflictReviewDialog
from .old_new_comparison import OldNewComparisonWindow
from .usage_guide import UsageGuideWindow

__all__ = ["OCRConflictReviewDialog", "OldNewComparisonWindow", "UsageGuideWindow"]
