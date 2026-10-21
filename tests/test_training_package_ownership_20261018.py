"""Physical training package ownership gate (Issue #562)."""
from pathlib import Path
import importlib

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
MOVED = ("training_export_page_understanding",
         "training_export_unified_layout", "training_export_v3")


def test_training_modules_are_physically_owned():
    for old in MOVED:
        assert not (ROOT / (old + ".py")).exists(), old
        assert (ROOT / "training" / (old.removeprefix("training_") + ".py")).is_file(), old


def test_training_imports_are_canonical():
    for old in MOVED:
        module = importlib.import_module("picture_capture.training." + old.removeprefix("training_"))
        assert module is not None


def test_new_training_owners_are_physical_and_importable():
    for former, owner in (
        ("training_baseline.py", "training/baseline.py"),
        ("training_export_composed.py", "training/export_composed.py"),
        ("training_export_complete_dialog.py", "training/export_complete_dialog.py"),
    ):
        assert not (ROOT / former).exists(), former
        assert (ROOT / owner).is_file(), owner
        module = importlib.import_module("picture_capture." + owner.removesuffix(".py").replace("/", "."))
        assert module is not None


def test_legacy_training_export_entrypoints_are_preserved():
    for name in ("training_export.py", "training_export_ui.py"):
        assert (ROOT / name).is_file()
