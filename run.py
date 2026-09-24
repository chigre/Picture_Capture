"""Picture Capture launcher.

This launcher never spawns or replaces the current process.  On Windows the
visible batch entry point may start this file with the virtual environment's
pythonw.exe; in that case stdout/stderr are redirected to a local log so Tk
callbacks do not fail when no console is attached.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
import traceback
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
_SRC = _PROJECT_ROOT / "src"
_LOG_PATH_ENV = "PC_LOG"


def _has_console() -> bool:
    return sys.stdout is not None and sys.stderr is not None


def _log_path() -> Path:
    override = os.environ.get(_LOG_PATH_ENV)
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Picture_Capture" / "launcher.log"


def _redirect_streams_to_log() -> None:
    if _has_console():
        return
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = path.open("a", encoding="utf-8", buffering=1)
    except OSError:
        return

    sys.stdout = stream
    sys.stderr = stream
    sys.__stdout__ = stream
    sys.__stderr__ = stream

    def _excepthook(exc_type, exc_value, exc_tb) -> None:
        traceback.print_exception(exc_type, exc_value, exc_tb, file=stream)
        stream.flush()

    sys.excepthook = _excepthook


def main() -> int:
    _redirect_streams_to_log()
    sys.path.insert(0, str(_SRC))
    from picture_capture.app import main as app_main

    return app_main()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
