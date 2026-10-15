from __future__ import annotations

import faulthandler
import os
import sys
import threading
import tkinter as tk


def _stage(message: str) -> None:
    print(f"[gui-smoke] {message}", flush=True)


def main() -> int:
    # Exercise the same explicit bootstrap path as the packaged script, run.py
    # and ``python -m picture_capture``. Importing app.py directly would miss
    # composition-root preparation and could hide startup regressions.
    from picture_capture.bootstrap.application import build_application

    app_module = build_application()
    PictureCaptureApp = app_module.PictureCaptureApp
    SettingsDialog = app_module.SettingsDialog
    UsageGuideWindow = app_module.UsageGuideWindow
    from picture_capture.environment_center import EnvironmentCenterWindow

    finished = threading.Event()

    def watchdog() -> None:
        if finished.wait(75):
            return
        _stage("TIMEOUT after 75 seconds; dumping all Python thread stacks")
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        os._exit(124)

    threading.Thread(
        target=watchdog, name="gui-smoke-watchdog", daemon=True,
    ).start()

    _stage("construct PictureCaptureApp through bootstrap-prepared module")
    app = PictureCaptureApp()
    try:
        _stage("PictureCaptureApp constructed")
        # Real UI bridge: the existing 画线…→插图关联 command must invoke
        # selected-scope processing, not the old current-page-only method.
        controller = app._illustration_controller_for_call()
        original_association = controller.associate_selected_scope
        association_calls = []
        try:
            controller.associate_selected_scope = lambda: association_calls.append("range")
            app.associate_illustrations()
        finally:
            controller.associate_selected_scope = original_association
        if association_calls != ["range"]:
            raise RuntimeError("Illustration association menu bridge is not batch-range aware")
        _stage("illustration association menu dispatches selected-scope controller")
        # Real Tk thumbnail column/controls smoke, without private scans.
        from tkinter import ttk
        thumbs = app._page_thumbnails
        if thumbs.tree.heading("#0", "text") != "缩略图":
            raise RuntimeError("Thumbnail header is not the first native Treeview column")
        if thumbs.row.winfo_manager() != "pack":
            raise RuntimeError("Thumbnail controls not placed under page navigation")
        if thumbs.enabled_var.get():
            raise RuntimeError("Thumbnails must default OFF for legacy projects")
        thumbs.enabled_var.set(True)
        thumbs.apply()
        if "tree" not in str(app.page_list.cget("show")):
            raise RuntimeError("First-column preview did not become visible")
        thumbs.width = 120
        thumbs.apply()
        if int(ttk.Style(app).lookup("PC.Treeview", "rowheight")) != 128:
            raise RuntimeError("Thumbnail resizing did not increase page-row height")
        app.workspace_mode = "紧凑"
        thumbs.on_mode_change()
        if "disabled" not in thumbs.toggle.state() or "tree" in str(app.page_list.cget("show")):
            raise RuntimeError("Compact mode did not disable and hide thumbnails")
        app.workspace_mode = "正常"
        thumbs.on_mode_change()
        if not thumbs.enabled_var.get() or "tree" not in str(app.page_list.cget("show")):
            raise RuntimeError("Returning to normal mode did not restore thumbnails")
        thumbs.enabled_var.set(False)
        thumbs.width = 80
        thumbs.apply()
        # Range selection is for batch operations, never a page-index filter.
        app.update_idletasks()
        full_row = app.page_range_controls_row
        if full_row.winfo_rooty() - app.sidebar.winfo_rooty() > 8:
            raise RuntimeError("Redundant top padding still leaves a blank gap above full page-range controls")
        full_modes = [
            str(button.cget("value")) for button in full_row.winfo_children()
        ]
        if full_modes != ["current", "to_end", "to_specified", "bookmarks"]:
            raise RuntimeError(f"Expected four batch-range choices in full mode: {full_modes}")
        last_radio = full_row.winfo_children()[-1]
        if (last_radio.winfo_rootx() + last_radio.winfo_width() >
                app.page_panel.winfo_rootx() + app.page_panel.winfo_width() + 2):
            raise RuntimeError("Bookmark range radio is clipped in normal full page-index width")
        _stage("full page range: no phantom row, bookmark radio present and uncut")

        _stage("page thumbnail controls smoke: OK")

        # The old smoke only asserted that the #0 column was visible; it never
        # loaded a real PNG or checked a Tk PhotoImage pixel. Exercise the real
        # full page index with entirely synthetic source images.
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from PIL import Image
        from picture_capture.page_thumbnail_cache import (
            thumbnail_cache_path, thumbnail_cache_dir,
            FINGERPRINT_KEY, SOURCE_FILENAME_KEY, source_fingerprint,
        )
        import time

        with TemporaryDirectory(prefix="pc-thumb-smoke-") as working:
            project_root = Path(working)
            scans = []
            colors = ((235, 25, 30), (25, 220, 40), (30, 60, 240))
            saved_project = app.project
            try:
                for index, color in enumerate(colors):
                    path = project_root / f"synthetic-{index}.png"
                    Image.new("RGB", (240, 340), color).save(path)
                    scans.append(path)
                    app.page_list.insert(
                        "", "end", iid=str(index),
                        values=("", path.stem, "", "", "", ""),
                    )
                app.project = SimpleNamespace(root=project_root, images=scans)
                # Bookmark range chooses work pages, not visible index rows.
                saved_bookmarks = list(app.settings.page_bookmarks)
                app.settings.page_bookmarks = ["synthetic-2", "synthetic-0"]
                try:
                    app.page_range_var.set("bookmarks")
                    if app.selected_page_indices() != [0, 2]:
                        raise RuntimeError("Bookmark batch scope must resolve saved page stems")
                    if len(app.page_list.get_children()) != 3:
                        raise RuntimeError("Bookmark scope incorrectly filtered the page index")
                    app.settings.page_bookmarks = []
                    if app.selected_page_indices() != []:
                        raise RuntimeError("An empty bookmark scope must select no work pages")
                finally:
                    app.settings.page_bookmarks = saved_bookmarks
                    app.page_range_var.set("current")
                thumbs.enabled_var.set(True)
                thumbs.apply()
                thumbs.project_rows_ready()
                app.update_idletasks()

                def pixel_for(iid: str):
                    raw = app.page_list.item(iid, "image")
                    if not raw:
                        return None
                    name = raw[0] if isinstance(raw, (tuple, list)) else raw
                    return tuple(int(v) for v in app.tk.splitlist(
                        app.tk.call(name, "get", 5, 5),
                    ))

                for _ in range(60):
                    app.update()
                    if all(pixel_for(str(i)) == colors[i] for i in range(3)):
                        break
                    time.sleep(0.03)
                else:
                    raise RuntimeError("Real thumbnails never loaded into native first-column cells")

                for i in range(3):
                    if not app.page_list.bbox(str(i), "#0"):
                        raise RuntimeError("Thumbnail first-column cell has no visible bbox")
                app.page_list.move("2", "", 0)
                app.update()
                if pixel_for("2") != colors[2] or pixel_for("0") != colors[0]:
                    raise RuntimeError("Sorting detached image pixels from their stable page iids")
                for _ in range(80):
                    app.update()
                    if all(thumbnail_cache_path(project_root, path).is_file() for path in scans):
                        break
                    time.sleep(0.03)
                else:
                    raise RuntimeError("All-page thumbnail cache did not fill the project folder")
                cache_files = list(thumbnail_cache_dir(project_root).iterdir())
                if sorted(file.name for file in cache_files) != [
                    f"synthetic-{i}.png" for i in range(3)
                ]:
                    raise RuntimeError("Cache must use original page stems in one flat directory")
                if not all(path.is_file() for path in cache_files):
                    raise RuntimeError("Flat thumbnail cache unexpectedly created nested directories")
                for path in scans:
                    with Image.open(thumbnail_cache_path(project_root, path)) as cached:
                        if cached.info.get(SOURCE_FILENAME_KEY) != path.name:
                            raise RuntimeError("Cached PNG source filename does not match its page")
                        if cached.info.get(FINGERPRINT_KEY) != source_fingerprint(path):
                            raise RuntimeError("Cached PNG source fingerprint does not match its page")
                from picture_capture.ui.page_list_grid import page_grid_segments

                def check_grid_column_alignment(label: str) -> None:
                    """Catch the native ttk heading separator's 5px grip offset."""
                    app.update_idletasks()
                    app._page_index_grid.repaint()
                    lines = page_grid_segments(app.page_list)
                    vertical = [x for x, _y, w, _h in lines if w == 1]
                    visible_rows = app._visible_page_list_iids()
                    if not visible_rows:
                        raise RuntimeError(f"{label}: no visible page index rows")
                    iid = visible_rows[0]
                    displayed = tuple(app.tk.splitlist(app.page_list.cget("displaycolumns")))
                    if not displayed or displayed == ("#all",):
                        displayed = tuple(app.tk.splitlist(app.page_list.cget("columns")))
                    shown = (("#0",) if "tree" in str(app.page_list.cget("show")) else ())
                    expected = []
                    for column in (*shown, *displayed):
                        cell = app.page_list.bbox(iid, column)
                        if not cell:
                            raise RuntimeError(f"{label}: missing displayed bbox {column}")
                        boundary = int(cell[0]) + int(cell[2]) - 1
                        if 0 < boundary < app.page_list.winfo_width():
                            expected.append(boundary)
                    if vertical != expected:
                        raise RuntimeError(
                            f"{label}: body dividers {vertical} do not match "
                            f"native heading/cell boundaries {expected}"
                        )

                app._page_index_grid.repaint()
                segments = page_grid_segments(app.page_list)
                if not any(width == 1 for _x, _y, width, _h in segments):
                    raise RuntimeError("No vertical cell gridlines found in real Tk Treeview")
                if not any(height == 1 for _x, _y, _w, height in segments):
                    raise RuntimeError("No horizontal cell gridlines found in real Tk Treeview")
                if app._page_index_grid.visible_segment_count != len(segments):
                    raise RuntimeError("Pale cell grid failed to place every visible divider")
                check_grid_column_alignment("initial viewport")
                horizontal_range = app.page_list.xview()
                if horizontal_range[1] - horizontal_range[0] < 0.99:
                    app.page_list.xview_moveto(1.0)
                    check_grid_column_alignment("horizontal scroll")
                    app.page_list.xview_moveto(0.0)
                    check_grid_column_alignment("horizontal scroll restored")
                _stage("page index grid: native heading/body divider pixels align")
                _stage("actual synthetic page images: visible pixels, sorted IDs, flat source-validated cache OK")

                # Previous smoke used THREE pages: it could never catch the
                # user's regression where only the initial nine rows showed
                # thumbnail pixels. Build enough pages for several viewports.
                extended_colors = {}
                for index in range(3, 36):
                    color = ((index * 5) % 256, (index * 7) % 256, (index * 11) % 256)
                    path = project_root / f"synthetic-{index}.png"
                    Image.new("RGB", (240, 340), color).save(path)
                    scans.append(path)
                    extended_colors[str(index)] = color
                    app.page_list.insert(
                        "", "end", iid=str(index),
                        values=("", path.stem, "", "", "", ""),
                    )
                thumbs.project_rows_ready()
                app.page_list.yview_moveto(1.0)
                app._schedule_page_cell_overlay_refresh()
                app.update_idletasks()
                bottom_iids = app._visible_page_list_iids()
                if not bottom_iids or max(int(iid) for iid in bottom_iids) < 25:
                    raise RuntimeError(f"Page-index viewport failed to scroll past page nine: {bottom_iids}")

                for _ in range(110):
                    app.update()
                    bottom_iids = app._visible_page_list_iids()
                    later = [iid for iid in bottom_iids if int(iid) >= 25]
                    if later and all(pixel_for(iid) == extended_colors[iid] for iid in later):
                        break
                    time.sleep(0.02)
                else:
                    raise RuntimeError(
                        "After scrolling, actual visible page thumbnails did not refresh: "
                        + str([(iid, pixel_for(iid)) for iid in bottom_iids])
                    )

                # Reorder a non-initial page to the top and check its true
                # scan pixels remain bound to the stable Treeview page iid.
                app.page_list.move("31", "", 0)
                app.page_list.yview_moveto(0.0)
                app._schedule_page_cell_overlay_refresh()
                for _ in range(110):
                    app.update()
                    if "31" in app._visible_page_list_iids() and pixel_for("31") == extended_colors["31"]:
                        break
                    time.sleep(0.02)
                else:
                    raise RuntimeError("Sorted/reordered page 31 displayed a stale or missing thumbnail")
                app._page_index_grid.repaint()
                lines_after_sort = page_grid_segments(app.page_list)
                if not lines_after_sort or app._page_index_grid.visible_segment_count != len(lines_after_sort):
                    raise RuntimeError("Cell borders vanished after scrolling/reordering page index")
                check_grid_column_alignment("scrolled/sorted 36-page index")
                _stage("thumbnails and cell borders after scrolling and sorting: OK")
                # A temporary synthetic project must not disappear while the
                # bounded background workers still publish thumbnail PNGs.
                # In particular Windows denies unlinking a worker-owned .tmp
                # while the background os.replace is in flight. Drain the
                # existing after/queue path and assert all pages are cached
                # before leaving this TemporaryDirectory.
                for _ in range(600):
                    app.update()
                    if (
                        thumbs._tasks.active == 0
                        and all(
                            thumbnail_cache_path(project_root, path).is_file()
                            for path in scans
                        )
                    ):
                        break
                    time.sleep(0.02)
                else:
                    raise RuntimeError(
                        "Synthetic thumbnail workers did not drain before "
                        "temporary project cleanup"
                    )
                if list(thumbnail_cache_dir(project_root).glob(".thumbnail-*.tmp")):
                    raise RuntimeError(
                        "Thumbnail workers left unfinished temp files"
                    )
                _stage("36-page cache jobs fully drained before temp project removal")
            finally:
                thumbs.enabled_var.set(False)
                thumbs.width = 80
                thumbs.apply()
                thumbs._clear_images()
                for iid in app.page_list.get_children():
                    app.page_list.delete(iid)
                app.project = saved_project

        if app._app_icon_photo is None:
            raise RuntimeError(
                "Packaged application icon failed to load: "
                + str(getattr(app, "_app_icon_error", None))
            )
        if not app._app_icon_registered:
            raise RuntimeError("Application icon could not be registered")
        app.withdraw()
        app.update_idletasks()
        _stage("root withdrawn")

        windows: list[tk.Toplevel] = []
        for name, factory in (
            ("EnvironmentCenterWindow", lambda: EnvironmentCenterWindow(app)),
            ("SettingsDialog", lambda: SettingsDialog(app)),
            ("UsageGuideWindow", lambda: UsageGuideWindow(app)),
        ):
            _stage(f"construct {name}")
            window = factory()
            windows.append(window)
            _stage(f"constructed {name}")
            if name == "SettingsDialog":
                # Real Tk construction/scroll smoke, not only source inspection.
                help_canvases = getattr(window, "_settings_help_scroll_canvases", [])
                if not help_canvases:
                    raise RuntimeError("Settings help has no independently scrollable canvases")
                window._show_settings_help("长说明换行测试", "说明：这是一段很长的中文参数说明。" * 90)
                window.update_idletasks()
                visible = [cv for cv in help_canvases if cv.winfo_ismapped()]
                if visible:
                    cv = visible[0]
                    if cv.bbox("all") is None:
                        raise RuntimeError("Settings help text has no scroll region")
                    cv.yview_moveto(1.0)
                    window.update_idletasks()
                    if cv.yview()[0] <= 0.0:
                        raise RuntimeError("Long Settings help did not overflow into scrollable region")
                    window._show_settings_help("另一设置", "短说明")
                    window.update_idletasks()
                    if cv.yview()[0] > 0.0:
                        raise RuntimeError("Switching Settings help did not reset scroll position")
            window.withdraw()
            window.update_idletasks()
            _stage(f"withdrew {name}")

        # Real Tk check for the inline ReviewWindow crop-side number.
        # No project, actual dictionary scan, or PDIC is loaded.
        _stage("review crop-side index widget smoke")
        from tkinter import ttk
        from picture_capture.ui.review_crop_sequence import (
            create_review_crop_with_index,
        )
        probe = tk.Frame(app)
        probe.parent = app
        probe.scroll_rows = lambda _event: None
        probe.scroll_rows_linux = lambda _delta: None
        crop_rows = ttk.Frame(probe)
        image = tk.PhotoImage(master=app, width=100, height=32)
        crop_widget, index_widget, crop_container = create_review_crop_with_index(
            probe, crop_rows, photo=image, index=9, total=10,
        )
        if index_widget.cget("text") != app._entry_sequence_text(9, 10):
            raise RuntimeError("Review index differs from main canvas number")
        if index_widget.cget("bg") != "#e6e6e6":
            raise RuntimeError("Review index lost its main-style background")
        if index_widget.grid_info().get("sticky") != "s":
            raise RuntimeError("Review index is not bottom-aligned to crop")
        if crop_widget.master is not index_widget.master:
            raise RuntimeError("Review number and crop have separate lifecycles")
        crop_container.destroy()
        if index_widget.winfo_exists() or crop_widget.winfo_exists():
            raise RuntimeError("Destroying a review row left an orphan number")
        probe.destroy()
        _stage("review crop-side index widget smoke: OK")

        for window in reversed(windows):
            _stage(f"destroy {window.__class__.__name__}")
            window.destroy()
        app.update_idletasks()
        _stage("secondary windows destroyed")
        print("GUI construction smoke: OK", flush=True)
        return 0
    finally:
        try:
            _stage("destroy root")
            app.destroy()
            _stage("root destroyed")
        except tk.TclError:
            pass
        finally:
            finished.set()


if __name__ == "__main__":
    raise SystemExit(main())
