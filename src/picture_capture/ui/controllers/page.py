from __future__ import annotations

"""Page-selection and asynchronous page-navigation orchestration.

The controller deliberately stops at ``app.load_page``.  Committing a decoded
page into the live Tk/application state remains in ``PictureCaptureApp`` for
this migration step; this module owns only navigation decisions and background
preloading.  Keeping that seam explicit lets later PRs move page-state commit
logic independently without turning ``PictureCaptureApp`` into a mixin stack.
"""

import json
from typing import Any

from PIL import Image

from ...appearance import themed_display_image
from ...formats import pdic_path, read_pdic, read_ppp
from ...image_utils import normalize_page_rgb
from ...page_sections import read_page_sections
from ...project_storage import ocr_cache_root, ppp_read_path_for_image


class PageController:
    """Coordinate page navigation while the Tk root remains the state owner."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def on_page_select(self, _event: Any) -> None:
        app = self.app
        if (
            getattr(app, "_batch_active", False)
            and not app._batch_foreground_pages
            and not getattr(app, "_batch_allow_page_navigation", False)
        ):
            if app.current_index >= 0 and tuple(app.page_list.selection()) != (str(app.current_index),):
                # Revert a rejected click only once. The correction itself
                # emits TreeviewSelect; subsequent callbacks must be no-ops.
                app._set_page_list_selection(app.current_index, ensure_visible=False)
            app.status_var.set("当前批量任务运行中，暂不允许切换页面；可先暂停/停止。")
            return
        selection = tuple(app.page_list.selection())
        if not selection:
            return
        focused = app.page_list.focus()
        chosen = focused if focused in selection else selection[-1]
        try:
            index = int(chosen)
        except (TypeError, ValueError):
            return
        if index != app.current_index:
            self.request_page_load(index)
        else:
            app._pending_page_index = None
            app._invalidate_ui_worker("page-load")

    def request_page_load(
        self,
        index: int,
        *,
        reset_zoom: bool = False,
        current_already_saved: bool = False,
        force: bool = False,
    ) -> bool:
        """Decode/read a target page off-thread, then commit it on the Tk thread."""
        app = self.app
        if not app.project or not (0 <= index < len(app.project.images)):
            return False
        if index == app.current_index and app.image is not None and not force:
            app._pending_page_index = None
            app._invalidate_ui_worker("page-load")
            app._set_page_list_selection(index, ensure_visible=True)
            return True
        if app._pending_page_index == index and not force:
            return True
        project = app.project
        page = project.images[index]
        project_root = project.root
        view_scale = float(app.view_scale)
        appearance_mode = app.appearance_mode
        app._pending_page_index = index
        app.status_var.set(f"正在后台加载 {page.name}…")

        def worker():
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            entries = read_pdic(pdic_path(page))
            polygons = read_ppp(ppp_read_path_for_image(page))
            page_sections = read_page_sections(page)
            cache_path = ocr_cache_root(project_root) / f"{page.stem}.json"
            ocr_payload: dict = {}
            if cache_path.exists():
                try:
                    loaded = json.loads(cache_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        ocr_payload = loaded
                except Exception:
                    ocr_payload = {}
            display_size = (
                max(1, round(image.width * view_scale)),
                max(1, round(image.height * view_scale)),
            )
            display_image = themed_display_image(
                image.resize(display_size, Image.Resampling.LANCZOS),
                appearance_mode,
            )
            return {
                "project_root": str(project_root),
                "index": index,
                "image": image,
                "entries": entries,
                "polygons": polygons,
                "page_sections": page_sections,
                "ocr_payload": ocr_payload,
                "display_size": display_size,
                "display_image": display_image,
                "view_scale": view_scale,
            }

        def done(payload) -> None:
            if app.project is not project:
                return
            app._pending_page_index = None
            app.load_page(
                index,
                reset_zoom=reset_zoom,
                preloaded=payload,
                skip_current_save=current_already_saved,
            )

        def failed(exc, detail) -> None:
            if detail:
                print(detail)
            if app.project is project:
                app._pending_page_index = None
                app.show_error(f"加载页面失败：{page.name}", exc)

        app._start_ui_worker("page-load", worker, done, failed)
        return True

    def change_page(
        self,
        delta: int,
        *,
        preloaded: dict | None = None,
        current_already_saved: bool = False,
        async_allowed: bool = True,
    ) -> bool:
        app = self.app
        if (
            getattr(app, "_batch_active", False)
            and not app._batch_foreground_pages
            and not getattr(app, "_batch_allow_page_navigation", False)
        ):
            app.status_var.set("当前批量任务运行中，暂不允许切换页面；可先暂停/停止。")
            return False
        if not app.project:
            return False
        base_index = (
            app._pending_page_index
            if app._pending_page_index is not None
            else app.current_index
        )
        target = base_index + delta
        if not 0 <= target < len(app.project.images):
            if (
                not current_already_saved
                and app._can_save_current_during_batch_navigation()
            ):
                app._save_current_page_by_mode()
            app.status_var.set("已经到起始页" if target < 0 else "已经到最末页")
            return False
        if preloaded is None and async_allowed:
            return self.request_page_load(
                target,
                current_already_saved=current_already_saved,
            )
        app.load_page(
            target,
            preloaded=preloaded,
            skip_current_save=current_already_saved,
        )
        return True


__all__ = ["PageController"]
