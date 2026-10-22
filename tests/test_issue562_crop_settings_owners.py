"""Issue #562: crop Settings helpers have physically canonical owners."""
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_crop_settings_ownership_and_exports():
    for former, canonical, exported in (
        ("single_line_merge_settings.py", "crop/single_line_merge_settings.py", "merge_page_line_images"),
        ("unlined_export_filter_settings.py", "crop/unlined_export_filter_settings.py", "load_unlined_filter_settings"),
    ):
        assert not (ROOT / former).exists()
        assert (ROOT / canonical).is_file()
        mod = import_module("picture_capture." + canonical[:-3].replace("/", "."))
        assert callable(getattr(mod, exported))


def test_crop_settings_import_callers_use_canonical_owner():
    for rel in ("crop/single_line_parallel.py", "crop/unlined_line_export.py", "ui/settings/crop.py", "ui/controllers/crop.py"):
        txt = (ROOT / rel).read_text(encoding="utf-8")
        # Crop implementations now share a package with the settings owners;
        # one-dot imports there are canonical, unlike retired root imports.
        if rel.startswith("crop/"):
            assert "from .single_line_merge_settings import" in txt
        else:
            assert "from .single_line_merge_settings import" not in txt
            assert "from .unlined_export_filter_settings import" not in txt
        assert "from .crop.single_line_merge_settings import" not in txt
        assert "from .crop.unlined_export_filter_settings import" not in txt
        assert "from ...single_line_merge_settings import" not in txt
        assert "from ...unlined_export_filter_settings import" not in txt
