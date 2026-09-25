from __future__ import annotations

import tkinter as tk


def main() -> int:
    from picture_capture.app import FontPickerDialog, PictureCaptureApp, SettingsDialog, UsageGuideWindow
    from picture_capture.environment_center import EnvironmentCenterWindow

    app = PictureCaptureApp()
    try:
        app.withdraw()
        app.update_idletasks()

        windows: list[tk.Toplevel] = []
        for factory in (
            lambda: EnvironmentCenterWindow(app),
            lambda: SettingsDialog(app),
            lambda: UsageGuideWindow(app),
            lambda: FontPickerDialog(
                app,
                title="字体选择 smoke",
                family="Arial",
                size=12,
                bold=False,
                italic=False,
                on_apply=lambda *_args: None,
            ),
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
