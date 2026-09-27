from __future__ import annotations

import tkinter as tk


def main() -> int:
    from picture_capture.app import PictureCaptureApp, SettingsDialog, UsageGuideWindow
    from picture_capture.environment_center import EnvironmentCenterWindow

    app = PictureCaptureApp()
    try:
        if app._app_icon_photo is None:
            raise RuntimeError(
                "Packaged application icon failed to load: "
                + str(getattr(app, "_app_icon_error", None))
            )
        if not app._app_icon_registered:
            raise RuntimeError("Application icon could not be registered")
        app.withdraw()
        app.update_idletasks()

        windows: list[tk.Toplevel] = []
        for factory in (
            lambda: EnvironmentCenterWindow(app),
            lambda: SettingsDialog(app),
            lambda: UsageGuideWindow(app),
        ):
            window = factory()
            windows.append(window)
            window.withdraw()
            window.update_idletasks()

        for window in reversed(windows):
            window.destroy()
        app.update_idletasks()
        print("GUI construction smoke: OK")
        return 0
    finally:
        try:
            app.destroy()
        except tk.TclError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
