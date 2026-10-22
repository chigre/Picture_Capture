"""Issue #562: canonical project-storage and SECTION owners, no old-root shims."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
REPO = ROOT.parents[1]
OWNERS = ("project_storage", "page_sections")


@pytest.mark.parametrize("name", OWNERS)
def test_persistence_owner_is_physical_and_importable(name: str):
    assert not (ROOT / (name + ".py")).exists()
    assert (ROOT / "persistence" / (name + ".py")).is_file()
    assert importlib.util.find_spec("picture_capture." + name) is None
    assert importlib.util.find_spec("picture_capture.persistence." + name) is not None


def test_source_uses_no_retired_storage_imports():
    for path in sorted(p for folder in ("src", "tests", "scripts")
                       for p in (REPO / folder).rglob("*.py")):
        if path.name == Path(__file__).name:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        within = path.parent.relative_to(ROOT).parts if path.is_relative_to(ROOT) else ()
        package = ("picture_capture", *within)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not any(node.value == "picture_capture." + old or
                               node.value.startswith("picture_capture." + old + ".")
                               for old in OWNERS), (path, node.lineno)
            if isinstance(node, ast.Import):
                assert all(name.name not in {"picture_capture.project_storage", "picture_capture.page_sections"}
                           for name in node.names), (path, node.lineno)
            elif isinstance(node, ast.ImportFrom):
                assert node.module not in {"picture_capture.project_storage", "picture_capture.page_sections"}, (path, node.lineno)
                if node.level and node.level <= len(package):
                    parent = package[:len(package) - node.level + 1]
                    mod = tuple((node.module or "").split(".")) if node.module else ()
                    if (node.module or "") in OWNERS:
                        assert parent != ("picture_capture",), (path, node.lineno)
                    elif not node.module and parent == ("picture_capture",):
                        assert all(item.name not in OWNERS for item in node.names), (path, node.lineno)
                elif node.module == "picture_capture":
                    assert all(item.name not in OWNERS for item in node.names), (path, node.lineno)


def test_critical_section_format_and_atomic_contract_remain_owned():
    text = (ROOT / "persistence" / "page_sections.py").read_text(encoding="utf-8")
    assert 'PAGE_SECTIONS_FORMAT = "picture-capture-page-sections-v2"' in text
    assert "_PAGE_SECTIONS_WRITE_LOCK" in text
    assert "os.replace(" in text
    assert "migrated_page_sections_path_for_image" in text


def test_managed_project_routing_remains_in_one_module():
    text = (ROOT / "persistence" / "project_storage.py").read_text(encoding="utf-8")
    assert "PROJECT_FORMAT_VERSION = 2" in text
    assert "def is_managed_project(" in text
    assert "def ensure_project_storage(" in text
    assert "_MANIFEST_WRITE_LOCK" in text
