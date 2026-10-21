"""Physical ownership invariants for independent auxiliary crop boundaries."""
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_auxiliary_owners_exist_without_compat_shims():
    for old, new, symbol in (
        ("auxiliary_lines.py", "crop/auxiliary_lines.py", "read_auxiliary_lines"),
        ("auxiliary_line_controller.py", "ui/auxiliary_line_controller.py", "AuxiliaryLineController"),
    ):
        assert not (ROOT / old).exists()
        assert (ROOT / new).is_file()
        obj = import_module("picture_capture." + new[:-3].replace("/", "."))
        assert hasattr(obj, symbol)


def test_root_application_binds_to_canonical_auxiliary_owner():
    txt = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "from .ui.auxiliary_line_controller import AuxiliaryLineController" in txt
    assert "from .crop.auxiliary_lines import AuxiliaryLineEdits" in txt
