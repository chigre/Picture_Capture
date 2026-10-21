"""Issue #562: canonical owners for Tk batch polling and line bookmarks."""
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_canonical_owners_exist_without_root_shims():
    cases = (
        ("batch_progress_budget", "ui/batch_progress_budget.py",
         "picture_capture.ui.batch_progress_budget", "batch_poll_should_yield"),
        ("line_diff_bookmarks", "refinement/line_diff_bookmarks.py",
         "picture_capture.refinement.line_diff_bookmarks", "page_has_manual_line_difference"),
    )
    for old, canonical, name, function in cases:
        assert not (ROOT / (old + ".py")).exists()
        assert (ROOT / canonical).is_file()
        assert callable(getattr(import_module(name), function))


def test_production_has_no_old_static_or_lazy_import_paths():
    obsolete = (
        "picture_capture.batch_progress_budget",
        "picture_capture.line_diff_bookmarks",
        "from .batch_progress_budget import",
        "from ..line_diff_bookmarks import",
    )
    for path in ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for old in obsolete:
            assert old not in source, f"{path.relative_to(ROOT)}: {old}"
