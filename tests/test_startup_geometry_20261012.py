"""Startup must not resize maximized -> compact before restoring a session."""
from pathlib import Path

import picture_capture.app as module


def test_saved_nonmaximized_presets_do_not_get_an_unnecessary_maximize():
    source = Path(module.__file__).read_text(encoding="utf-8")
    init = source.split("class PictureCaptureApp(tk.Tk):", 1)[1].split(
        "    def destroy(self)", 1
    )[0]
    assert 'if self.workspace_mode == "最大":' in init
    assert 'self.after_idle(self._maximize_main_window)' in init
    assert init.index('if self.workspace_mode == "最大":') < init.index(
        'self.after_idle(self._maximize_main_window)'
    )
    assert init.index('self.after_idle(self._maximize_main_window)') < init.index(
        'self.after_idle(self.restore_last_session)'
    )


def test_bat_launch_is_a_pure_direct_runtime_path():
    root = Path(module.__file__).resolve().parents[2]
    bat = (root / "run_windows.bat").read_text(encoding="utf-8")
    assert '".venv\\Scripts\\python.exe" "run.py"' in bat
    assert 'if not exist ".venv\\Scripts\\python.exe"' in bat
    for forbidden in ("uv sync", "uv run", "pip install", "curl", "powershell"):
        assert forbidden not in bat.lower()
