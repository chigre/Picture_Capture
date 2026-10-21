"""Issue #562: canonical platform-aware Tk helpers without root shims."""
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_ui_compat_is_physically_ui_owned():
    assert not (ROOT / "ui_compat.py").exists()
    assert (ROOT / "ui/compat.py").is_file()
    m = import_module("picture_capture.ui.compat")
    assert callable(m.resolve_content_font_family)
    assert callable(m.fit_window_to_work_area)
