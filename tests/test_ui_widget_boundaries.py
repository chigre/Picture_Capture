from __future__ import annotations

from pathlib import Path

from picture_capture.app import VerticalWordText as AppVerticalWordText
from picture_capture.ui.widgets.vertical_word import VerticalWordText


ROOT = Path(__file__).resolve().parents[1]


def test_vertical_word_widget_has_stable_direct_import_and_app_compatibility_alias() -> None:
    assert AppVerticalWordText is VerticalWordText
    assert VerticalWordText.__module__ == "picture_capture.ui.widgets.vertical_word"
    assert VerticalWordText._entry_index(0) == "1.0"
    assert VerticalWordText._entry_index("end") == "end-1c"


def test_vertical_word_widget_module_is_independent_from_app_module() -> None:
    source = (
        ROOT / "src" / "picture_capture" / "ui" / "widgets" / "vertical_word.py"
    ).read_text(encoding="utf-8")
    app_source = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")

    assert "from ...app" not in source
    assert "import picture_capture.app" not in source
    assert "class VerticalWordText" in source
    assert "class VerticalWordText" not in app_source
    assert "from .ui.widgets.vertical_word import VerticalWordText" in app_source
