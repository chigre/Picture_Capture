"""#562: grouped I/O physical owners and PDIC GUI call-time identity."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from picture_capture.io import formats, gui_io, picdic


def test_io_triple_owners_are_real_and_retired_modules_absent() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    for old, fn in (
        ("formats", "write_pdic"),
        ("gui_io", "read_pdic"),
        ("picdic", "build_picdic_package"),
    ):
        assert not (root / (old + ".py")).exists()
        assert (root / "io" / (old + ".py")).is_file()
        assert importlib.util.find_spec("picture_capture." + old) is None
        assert importlib.util.find_spec("picture_capture.io." + old) is not None
        assert callable(getattr({"formats": formats, "gui_io": gui_io, "picdic": picdic}[old], fn))


def test_gui_io_references_current_pdic_format_module_without_installers() -> None:
    from picture_capture import app
    assert gui_io._formats is formats
    assert app.write_pdic is gui_io.write_pdic
    assert app.read_pdic is gui_io.read_pdic
    assert app.pdic_path is gui_io.pdic_path


def test_picdic_and_gui_io_relocated_with_real_symbols() -> None:
    assert picdic.PicDicBuildCancelled.__module__ == "picture_capture.io.picdic"
    assert formats.Entry.__module__ == "picture_capture.models"
    assert gui_io.write_pdic.__module__.startswith("picture_capture.")
