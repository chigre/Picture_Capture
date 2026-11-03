"""Read-only ProjectState/scan-epoch owner for late focused crop callbacks.

A cheap in-memory session identity check. PDIC/OCR/SECTION byte witnesses
remain owned by their existing crop and publication boundaries; this helper
does not hash pages or touch Tk widgets.
"""
from __future__ import annotations


def crop_session_is_current(self) -> bool:
    """Check cheap ProjectState and scan-epoch ownership for crop callbacks.

    Content byte witnesses remain at worker and publication boundaries.
    This does not hash PDIC/OCR/SECTION on every prefetch completion, and
    legacy helper mocks without an epoch witness map keep their ABI.
    """
    if getattr(self, "_filter_scan_epoch_source_witnesses", None) is None:
        return True
    project = getattr(getattr(self, "parent", None), "project", None)
    owner = getattr(self, "_filter_scan_epoch_project", None)
    if project is None or project is not owner:
        return False
    if (
        getattr(self, "_filter_scan_epoch_invalidated", False)
        or getattr(self, "_filter_scan_epoch_source_serial", None)
        != getattr(self, "_filter_scan_serial", None)
    ):
        return False
    try:
        return bool(
            str(project.root)
            == str(getattr(self, "_filter_scan_epoch_project_root", None))
            and tuple(str(page) for page in project.images)
            == tuple(str(page) for page in self._filter_scan_epoch_pages)
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return False


