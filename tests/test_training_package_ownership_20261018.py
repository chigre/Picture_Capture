"""Physical training package ownership gate (Issue #562)."""
from pathlib import Path
import importlib

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
MOVED = ("training_baseline", "training_export", "training_export_complete_dialog",
         "training_export_composed", "training_export_page_understanding",
         "training_export_unified_layout", "training_export_v3")


def test_training_modules_are_physically_owned():
    for old in MOVED:
        assert not (ROOT / (old + ".py")).exists(), old
        assert (ROOT / "training" / (old.removeprefix("training_") + ".py")).is_file(), old


def test_training_imports_are_canonical():
    for old in MOVED:
        module = importlib.import_module("picture_capture.training." + old.removeprefix("training_"))
        assert module is not None


def test_legacy_training_export_ui_compatibility_entry_is_preserved():
    assert (ROOT / "training_export_ui.py").is_file()
