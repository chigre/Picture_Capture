"""Byte-level source ownership for focused-review scan target caches.

This read-only leaf verifies PDIC/OCR/SECTION evidence without importing
the Tk app or mutating the source files. Its callable remains re-exported
by focused_filter_workflow for existing patchpoints.
"""
from __future__ import annotations

from ..proofreading.focused_crop_source_fingerprint import (
    _source_page_index, verify_focused_scan_source,
)


def _focused_scan_target_source_signature(
    targets: list[dict], pages: list, project_root, deps,
) -> tuple:
    """Verify that visible scan targets still belong to their PDIC/OCR/SECTION inputs.

    Legacy synthetic callers with no scan witness retain their old helper ABI;
    real filter targets all carry a witness captured by scan_page().
    """
    expected_by_page = {}
    missing_pages = set()
    for target in targets:
        page_index = _source_page_index(target["page_index"])
        expected = target.get("_focused_scan_source_witness")
        if expected is None:
            missing_pages.add(page_index)
            continue
        if not 0 <= page_index < len(pages):
            raise ValueError("focused scan page index out of range")
        previous = expected_by_page.get(page_index)
        if previous is not None and previous != expected:
            raise RuntimeError("同一页面的重点筛选来源证明不一致")
        expected_by_page[page_index] = expected
    if missing_pages.intersection(expected_by_page):
        raise RuntimeError("重点筛选行缺少一致的数据来源证明")
    for page_index, expected in sorted(expected_by_page.items()):
        page = pages[page_index]
        cache_path = deps.ocr_cache_root(project_root) / f"{page.stem}.json"
        verify_focused_scan_source(
            page, deps.pdic_path(page), cache_path, expected,
        )
    return tuple(sorted(expected_by_page.items()))


