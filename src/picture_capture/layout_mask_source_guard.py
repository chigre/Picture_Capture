"""Side-effect-free source identity checks for the Layout illustration reuse option."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .project_storage import ppp_read_path_for_image


def detection_mask_source_path(page: Path, settings: Any, *, ordinary: bool) -> Path | None:
    """Keep auto-PPP persistence restricted to its existing ordinary workflow.

    OCR and combined algorithms can reuse saved polygons by reading the page
    path; their auto-mask path remains in-memory and must not mutate user PPP.
    """
    if ordinary or bool(getattr(settings, "layout_mask_illustrations_use_existing", False)):
        return Path(page)
    return None


def missing_saved_illustrations(pages: Iterable[Path], settings: Any) -> list[Path]:
    """Check *all* pages before a drawing batch rewrites any PDIC.

    Missing PPP in reuse mode is an error, never permission to auto-detect or
    silently fabricate an empty polygon set.
    """
    if not (bool(getattr(settings, "layout_mask_illustrations", False))
            and bool(getattr(settings, "layout_mask_illustrations_use_existing", False))):
        return []
    return [Path(page) for page in pages
            if not ppp_read_path_for_image(Path(page)).is_file()]


def saved_illustration_stamp(page: Path | None, settings: Any) -> tuple[Any, ...] | None:
    """Invalidate read-only Layout overlays when saved PPP changes or appears."""
    if page is None or not (
        bool(getattr(settings, "layout_mask_illustrations", False))
        and bool(getattr(settings, "layout_mask_illustrations_use_existing", False))
    ):
        return None
    path = ppp_read_path_for_image(Path(page))
    try:
        stat = path.stat()
        return (str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return (str(path), "missing")
