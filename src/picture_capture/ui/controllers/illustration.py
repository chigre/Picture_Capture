from __future__ import annotations

"""User-action orchestration for illustration detection workflows.

Phase 4M moved the stable selected-scope illustration detection entry seam.
Phase 4N moved the stable illustration-crop action entry. Phase 4O moves the
bounded illustration-crop runner orchestration while retaining the parallel
runner and path-policy boundaries on ``PictureCaptureApp``. Detection/crop
algorithms remain outside this controller.
"""

from dataclasses import replace
from pathlib import Path
from tkinter import messagebox
from typing import Any

from .crop import complete_crop_widths
from ...formats import pdic_path, read_ppp, write_ppp
from ...models import PolygonRegion
from ...illustration_labels import illustration_labels, label_text, user_edited_link
from ..illustration_association_dialog import confirm_illustration_association
from ...processing import (
    append_crop_log, append_illustration_crop_log, detect_illustrations_job,
    split_illustrations_job,
)
from ...project_storage import qt_root


class IllustrationController:
    """Coordinate selected-scope illustration detection without owning algorithms."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def preview_labels(self) -> list[str]:
        """Read-only visible captions in the same SECTION/column order as PDIC."""
        app = self.app
        if not getattr(app, "polygons", None) or app.current_page is None:
            return []
        return illustration_labels(
            app.polygons, app.current_page.stem,
            app._get_cached_display_geometry(),
            app.page_sections,
        )

    def persist_current(
        self, proposed: list[PolygonRegion] | None = None,
        *, associate: bool = False, redraw: bool = False,
    ) -> bool:
        """Atomic disk-first PPP commit; publish edited labels only on success.

        Staged PolygonRegion copies prevent write failures from partially
        renumbering the live objects or changing their geometry/selection.
        """
        app = self.app
        page = getattr(app, "current_page", None)
        if page is None:
            return False
        current = list(app.polygons if proposed is None else proposed)
        try:
            labels = illustration_labels(
                current, page.stem, app._get_cached_display_geometry(),
                app.page_sections,
                entries=list(app._ordered_entries_reading_order()) if associate else (),
                associate=associate,
            )
            staged = [
                PolygonRegion(label, list(region.points))
                for region, label in zip(current, labels)
            ]
            changed = write_ppp(app._ppp_write_path(page), staged, page.stem)
        except Exception as exc:
            # The canonical PPP writer uses atomic replacement. If its
            # post-write sidecar hook failed, prefer the persisted source over
            # the prior live snapshot and report the non-atomic hook failure.
            try:
                on_disk = read_ppp(app._ppp_read_path(page))
                if on_disk and (
                    [(r.label, r.points) for r in on_disk]
                    != [(r.label, r.points) for r in app.polygons]
                ):
                    app.polygons = on_disk
                    if redraw:
                        app.redraw()
            except Exception:
                pass
            app.show_error("保存PPP插图失败", exc)
            return False
        for region, label in zip(current, labels):
            region.label = label
        if proposed is not None:
            app.polygons = current
        if hasattr(app, "_update_page_row"):
            app._update_page_row(app.current_index)
        if redraw:
            app.redraw()
        return bool(changed)

    def add_manual_polygon(self, points: list[tuple[int, int]]) -> bool:
        app = self.app
        if len(points) < 3:
            return False
        if getattr(app, "_batch_active", False) and getattr(app, "_batch_allow_pdic_edits", False):
            app.status_var.set("插图识别期间暂不修改 PPP。")
            return False
        if not app.current_page:
            return False
        # The generated label is the only editable identifier. No prompt for a
        # legacy arbitrary name (which could invalidate AUTO provenance).
        added = PolygonRegion("", list(points))
        before = len(app.polygons)
        ok = self.persist_current(list(app.polygons) + [added], redraw=True)
        # write_ppp reports False on an unchanged file, but an actual addition
        # always changes bytes unless another process changed the target.
        return ok or len(app.polygons) > before

    def delete_polygon(self, region: PolygonRegion) -> bool:
        app = self.app
        if not app.current_page or region not in app.polygons:
            return False
        if getattr(app, "_batch_active", False) and getattr(app, "_batch_allow_pdic_edits", False):
            app.status_var.set("插图识别期间暂不修改 PPP。")
            return False
        before = len(app.polygons)
        remaining = [candidate for candidate in app.polygons if candidate is not region]
        success = self.persist_current(remaining, redraw=True)
        return bool(success or len(app.polygons) == before - 1)

    def update_label(self, region: PolygonRegion, typed: str) -> bool:
        app = self.app
        if region not in app.polygons or app.current_page is None:
            return False
        if getattr(app, "_batch_active", False) and getattr(app, "_batch_allow_pdic_edits", False):
            return False
        try:
            index = next(i for i, r in enumerate(app.polygons) if r is region)
            canonical = self.preview_labels()
            old = canonical[index]
            updated = user_edited_link(old, typed)
            if updated == old and region.label == updated:
                return True
            proposed = [PolygonRegion(r.label, list(r.points)) for r in app.polygons]
            proposed[index].label = updated
        except Exception as exc:
            app.show_error("插图标签无效", exc)
            return False
        return self.persist_current(proposed, redraw=True) or (
            list(app.polygons)[index].label == updated
        )

    def associate_current_page(self) -> None:
        app = self.app
        if not app.guard():
            return
        if not app.polygons:
            app.status_var.set("本页没有插图，未进行关联。")
            return
        if not confirm_illustration_association(app):
            return
        if getattr(app, "polygon_draw_var", None) is not None and app.polygon_draw_var.get():
            app.status_var.set("请先结束【编辑插图】，再进行插图关联。")
            return
        # Refresh live text edits only after confirmation; no PDIC rewrite is
        # performed. Association uses the current canonical reading order.
        app._sync_entry_editor_texts()
        app._sync_polygon_label_texts()
        # Always re-link (including clearing stale associations if a word was
        # removed); first persist, then update UI.
        before = [r.label for r in app.polygons]
        success = self.persist_current(associate=True, redraw=True)
        if success or [r.label for r in app.polygons] != before:
            total = len(app.polygons)
            linked = sum(
                label_text(region.label).split("|")[-1] != "xxx"
                for region in app.polygons
            )
            app.status_var.set(f"插图关联已保存：{total} 个插图，{linked} 个关联到上方词条，{total - linked} 个未匹配")
        elif [r.label for r in app.polygons] == before:
            app.status_var.set("插图关联结果未变化；PPP 已核对。")

    def split_illustrations_selected_scope(self) -> None:
        app = self.app
        if app._batch_active:
            app.status_var.set("已有批量任务正在运行，请结束后再执行插图切图。")
            return
        if not app.project or not app.current_page or app.image is None:
            messagebox.showinfo(
                "尚未打开",
                "请先打开包含扫描图片的项目目录。",
                parent=app,
            )
            return
        try:
            indices = app.selected_page_indices()
        except Exception as exc:
            app.show_error("页面范围无效", exc)
            return
        if not indices:
            return

        # A PPP decision may depend on the current entry text and geometry.
        # Commit visible PDIC edits before child workers load sidecars.
        try:
            flush = getattr(app, "_flush_deferred_page_save", None)
            if callable(flush):
                flush()
            save = getattr(app, "save_pdic", None)
            if callable(save):
                save(silent=True)
        except Exception as exc:
            app.show_error("插图切图前保存当前词条失败", exc)
            return
        app._sync_polygon_label_texts()
        write_ppp(
            app._ppp_write_path(app.current_page),
            app.polygons,
            app.current_page.stem,
        )
        app._start_illustration_crop(indices, app._load_crop_settings())

    def _start_illustration_crop(self, indices: list[int], config: dict) -> None:
        """Start PPP illustration export from the shared crop-settings snapshot."""
        app = self.app
        if not app.project or app._batch_active:
            if app._batch_active:
                app.status_var.set("已有批量任务正在运行，未启动插图切图。")
            return
        project = app.project
        settings = replace(app.settings)
        out_dir = qt_root(project.root) / "PIC"
        general_top = int(config.get("general_top_y", settings.start_y))
        general_bottom = int(config.get("general_bottom_y", 0))
        margin = int(config.get("polygon_margin", 0))
        entry_left = int(config.get("entry_left_padding_x", 0))
        entry_right = int(config.get("entry_right_padding_x", 0))
        integrate_illustrations = bool(config.get("integrate_illustrations", True))
        specials = config.get("special_pages", {}) if isinstance(config.get("special_pages", {}), dict) else {}
        workers = int(config.get("parallel_workers", settings.crop_parallel_workers))

        def job_builder(index: int, _position: int, _total: int):
            page = project.images[index]
            special = specials.get(page.stem, {}) if isinstance(specials.get(page.stem, {}), dict) else {}
            top_y = int(special.get("top_y", general_top))
            bottom_y = int(special.get("bottom_y", general_bottom))
            return (
                str(page), str(app._ppp_read_path(page)), str(out_dir), settings,
                top_y, bottom_y, margin, str(pdic_path(page)), entry_left, entry_right, integrate_illustrations,
                index,
                *((True,) if config.get("illustration_transparent_background", False) else ()),
            )

        def consume_result(_index: int, result):
            records = list(getattr(result, "records", []) or [])
            events = list(getattr(result, "events", []) or [])
            append_crop_log(project.root, records)
            append_illustration_crop_log(project.root, events)
            return len(records)

        def done(completed, total_pages, stopped, results, error):
            if error is not None:
                return
            count = sum(int(v or 0) for v in results)
            if stopped:
                app.status_var.set(f"插图切图已停止：完成 {completed}/{total_pages} 页，共导出 {count} 张")
            else:
                complete_crop_widths(app, project.root, config,
                                     f"插图切图完成：{completed} 页，共 {count} 张")

        app._start_parallel_batch_task(
            "插图切图", indices, split_illustrations_job, job_builder, consume_result, done,
            item_label=lambda i: project.images[i].name,
            max_workers=workers,
        )

    def detect_illustrations_selected_scope(self) -> None:
        app = self.app
        if app._batch_active:
            app.status_var.set("已有批量任务正在运行，请结束后再执行插图识别。")
            return
        if not app.project or not app.current_page or app.image is None:
            messagebox.showinfo(
                "尚未打开",
                "请先打开包含扫描图片的项目目录。",
                parent=app,
            )
            return
        try:
            indices = app.selected_page_indices()
        except Exception as exc:
            app.show_error("页面范围无效", exc)
            return
        if not indices:
            return

        # Preserve the foreground PPP commit point before the confirmation
        # dialog and before the worker snapshots the selected range.
        write_ppp(
            app._ppp_write_path(app.current_page),
            app.polygons,
            app.current_page.stem,
        )
        first = app.project.images[indices[0]].name
        last = app.project.images[indices[-1]].name
        if not messagebox.askyesno(
            "插图识别",
            f"将在所选范围自动识别插图并写入 PPP：\n{first} → {last}（共 {len(indices)} 页）\n\n"
            "人工绘制的 PPP 多边形会保留；再次识别只替换此前自动生成的 AUTO 区域。\n"
            "识别结果可继续用“绘制插图多边形”手工修正。\n\n开始识别？",
            parent=app,
        ):
            return

        project = app.project
        settings = replace(app.settings)

        def job_builder(index: int, _position: int, _total: int):
            # Passing immutable per-page arguments to the spawn-safe worker
            # prevents child processes from touching Tk widgets or app state.
            return (str(project.images[index]), settings, index)

        def done(completed, total_pages, stopped, results, error):
            if error is not None:
                return
            auto_count = sum(int((result or {}).get("auto", 0)) for result in results)
            if stopped:
                app.status_var.set(
                    f"插图识别已停止：完成 {completed}/{total_pages} 页，自动识别 {auto_count} 个插图区域"
                )
            else:
                app.status_var.set(
                    f"插图识别完成：{completed} 页，自动识别 {auto_count} 个插图区域；人工 PPP 已保留"
                )
            if app.current_index in indices and app.current_page is not None:
                app.polygons = read_ppp(app._ppp_read_path(app.current_page))
                app._update_page_row(app.current_index)
                app.polygon_var.set(True)
                app.redraw()

        app._start_parallel_batch_task(
            "插图识别", indices, detect_illustrations_job, job_builder,
            on_done=done,
            item_label=lambda index: project.images[index].name,
            max_workers=max(0, min(8, int(getattr(settings, "illustration_detect_parallel_workers", 0)))),
            allow_page_navigation=True,
            allow_pdic_edits=True,
        )
