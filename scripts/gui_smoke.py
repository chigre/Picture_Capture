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
        if int(ttk.Style(app).lookup("PC.Treeview", "rowheight")) != 176:
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
                _stage("actual synthetic page images: visible pixels, sorted IDs, flat source-validated cache OK")
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
