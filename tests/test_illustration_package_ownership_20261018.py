from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"

def test_illustration_package_exists():
    assert (ROOT / "illustration" / "__init__.py").is_file()

def test_illustration_modules_have_no_root_duplicates():
    names = ("illustrated_entries", "illustrated_export", "illustrated_geometry", "illustrated_guides", "illustrated_ocr", "illustrated_profile", "illustration_delete_geometry", "illustration_delete_overlay", "illustration_fill_opacity", "illustration_polygon_edit")
    for name in names:
        assert not (ROOT / (name + ".py")).exists()
