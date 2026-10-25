from __future__ import annotations

"""Current-page drawing task orchestration outside the legacy Tk controller.

The adapter passes a live dependency resolver rather than freezing its module
globals at import time. This preserves the existing monkeypatch seams for
detection, geometry, image decoding and OCR review across the three entry
modes. Only the Tk owner schedules work and applies the GUI completion result;
inference stays in detection.current_page_worker.
"""

from typing import Any, Callable, Mapping


def run_current_page_detection(
    app: Any,
    *,
    clicked_x: int | None,
    force_paddle_refresh: bool,
    dependencies: Callable[[], Mapping[str, Any]],
) -> None:
    """Prepare, schedule and apply one currently selected page's detection."""
    live = dependencies()
    snapshot = live["prepare_current_page_detection"](
        app,
        deps={
            "replace": live["replace"],
            "missing_saved_illustrations": live["missing_saved_illustrations"],
            "ocr_cache_root": live["ocr_cache_root"],
            "headword_filter_rules_path": live["headword_filter_rules_path"],
            "HEADWORD_FILTER_RULES_FILENAME": live["HEADWORD_FILTER_RULES_FILENAME"],
        },
    )
    if snapshot is None:
        return

    project = snapshot.project
    page = snapshot.page
    settings = snapshot.settings

    def worker(_item, _position: int, _total: int):
        current = dependencies()
        return current["detect_current_page"](
            page, project.root, settings,
            page_index=snapshot.page_index,
            page_sections=snapshot.page_sections,
            cache_path=snapshot.cache_path,
            filter_path=snapshot.filter_path,
            force_paddle_refresh=force_paddle_refresh,
            deps={
                "Image": current["Image"],
                "normalize_page_rgb": current["normalize_page_rgb"],
                "detect_entries": current["detect_entries"],
                "detection_mask_source_path": current["detection_mask_source_path"],
                "ocr_existing_entry_words_from_markers":
                    current["ocr_existing_entry_words_from_markers"],
                "load_replace_rules": current["load_replace_rules"],
                "replace_rules_path": current["replace_rules_path"],
                "project_profile_path": current["project_profile_path"],
            },
        )

    def done(_completed, _total, stopped, results, error):
        current = dependencies()
        return current["apply_current_page_detection_result"](
            app,
            project=project,
            page=page,
            settings=settings,
            existing_entries=snapshot.existing_entries,
            clicked_x=clicked_x,
            stopped=stopped,
            results=results,
            error=error,
            deps={
                "column_index_for_click": current["column_index_for_click"],
                "column_index": current["column_index"],
                "ocr_cache_root": current["ocr_cache_root"],
            },
        )

    label = {
        "combined": "融合画线 当前页识别",
        "paddleocr": "OCR画线 当前页识别",
    }.get(settings.detection_method, "当前页自动画线")
    app._start_batch_task(
        label, [snapshot.page_index], worker, done,
        item_label=lambda _item: page.name,
        refresh_page_quality=settings.detection_method in {"paddleocr", "combined"},
    )
