from __future__ import annotations

"""Snapshot and preflight for single-page drawing before any worker starts.

This owner contains no Tk widgets and performs no writes. It records the
active project, source page, settings, SECTION and unsaved entries for the
subsequent detection callback to use when checking stale results. Dynamic
dependencies retain historical controller monkeypatch points.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class CurrentPageDetectionSnapshot:
    project: Any
    page: Path
    page_index: int
    settings: Any
    page_sections: list[Any]
    existing_entries: list[Any]
    cache_path: Path | None
    filter_path: Path | None


def prepare_current_page_detection(
    app: Any,
    *,
    deps: Mapping[str, Any],
) -> CurrentPageDetectionSnapshot | None:
    """Run original guards, then snapshot all worker/callback page state."""
    if app._batch_active:
        app.status_var.set("后台画线任务运行中，暂不启动前台自动识别；可进行人工校对。")
        return None
    if not app.guard():
        return None
    if not app._guard_transformed_geometry("自动画线"):
        return None

    project = app.project
    page = app.current_page
    if deps["missing_saved_illustrations"]((page,), app.settings):
        app.status_var.set(
            "当前页缺少 PPP 插图数据：请先识别插图，或在设置中心→插图关闭‘使用已有的插图数据’。"
        )
        return None

    page_index = int(app.current_index)
    settings = deps["replace"](app.settings)
    page_sections = list(app.page_sections)
    existing_entries = [deps["replace"](entry) for entry in app.entries]
    ocr_mode = settings.detection_method in {"paddleocr", "combined"}
    cache_path = (
        deps["ocr_cache_root"](project.root) / f"{page.stem}.json"
        if ocr_mode else None
    )
    filter_path = (
        deps["headword_filter_rules_path"](
            project.root, deps["HEADWORD_FILTER_RULES_FILENAME"]
        )
        if ocr_mode else None
    )
    return CurrentPageDetectionSnapshot(
        project=project,
        page=page,
        page_index=page_index,
        settings=settings,
        page_sections=page_sections,
        existing_entries=existing_entries,
        cache_path=cache_path,
        filter_path=filter_path,
    )
