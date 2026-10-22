"""Issue #562: five page utility owners are physical, not root compatibility shims."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE / "src" / "picture_capture"
OWNERS = {
    "coordinate_space": "geometry.coordinate_space",
    "layout_transform": "geometry.layout_transform",
    "page_list_helpers": "project.page_list_helpers",
    "page_word_mapping": "proofreading.page_word_mapping",
    "pdic_restore": "proofreading.pdic_restore",
    "auxiliary_crop_partition": "crop.auxiliary_partition",
}

def _retired_relative_root_import(path: Path, item: ast.ImportFrom, retired: str) -> bool:
    if item.level <= 0 or (item.module or "") != retired:
        return False
    try:
        relative_dir = path.parent.relative_to(ROOT)
    except ValueError:
        # Non-package tests/scripts are not authorized to import removed helpers.
        return True
    package_parts = ("picture_capture", *relative_dir.parts)
    if item.level > len(package_parts):
        return True
    target = package_parts[:len(package_parts) - (item.level - 1)] + (retired,)
    return target == ("picture_capture", retired)


@pytest.mark.parametrize("retired, target", sorted(OWNERS.items()))
def test_page_utilities_have_one_canonical_owner(retired: str, target: str) -> None:
    assert not (ROOT / f"{retired}.py").exists()
    assert (ROOT / (target.replace(".", "/") + ".py")).is_file()
    assert importlib.util.find_spec("picture_capture." + retired) is None
    assert importlib.util.find_spec("picture_capture." + target) is not None


def test_no_retired_python_imports_in_source_tests_or_scripts() -> None:
    for parent in (BASE / "src", BASE / "tests", BASE / "scripts"):
        for path in parent.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for item in ast.walk(tree):
                if isinstance(item, ast.Import):
                    assert not any(n.name == "picture_capture." + retired or
                                   n.name.startswith("picture_capture." + retired + ".")
                                   for n in item.names for retired in OWNERS), (path, item.lineno)
                elif isinstance(item, ast.ImportFrom):
                    mod = item.module or ""
                    assert not any(mod == "picture_capture." + retired or
                                   mod.startswith("picture_capture." + retired + ".") or
                                   _retired_relative_root_import(path, item, retired)
                                   for retired in OWNERS), (path, item.lineno)
                    if mod in ("", "picture_capture"):
                        assert not any(n.name in OWNERS for n in item.names), (path, item.lineno)


def test_preserve_high_risk_root_entrypoints() -> None:
    for name in ("app", "processing_core", "page_sections", "layout_rows_cache",
                 "project_storage", "ocr_page_resume"):
        assert (ROOT / (name + ".py")).is_file()
