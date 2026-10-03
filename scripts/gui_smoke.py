from __future__ import annotations

import faulthandler
import os
import sys
import threading
import tkinter as tk


def _stage(message: str) -> None:
    print(f"[gui-smoke] {message}", flush=True)


def main() -> int:
    # Exercise the same launcher preparation path as run.py / python -m
    # picture_capture.  Importing app.py directly would miss launcher-only
    # compatibility patches and previously allowed startup regressions to pass
    # CI even though the downloaded branch could not construct the main window.
    from picture_capture.launcher import prepare_app_module

    app_module = prepare_app_module()
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

    _stage("construct PictureCaptureApp through launcher-prepared module")
    app = PictureCaptureApp()
    try:
        _stage("PictureCaptureApp constructed")
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
            window.withdraw()
            window.update_idletasks()
            _stage(f"withdrew {name}")

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
