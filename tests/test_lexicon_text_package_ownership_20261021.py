"""Issue #562: lexicon and text ownership is physical and importable."""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
OWNERS = {
    "cc_cedict": "lexicon/cc_cedict.py",
    "chinese_simplify": "lexicon/chinese_simplify.py",
    "collation": "lexicon/collation.py",
    "network_lookup": "lexicon/network_lookup.py",
    "latin_glued_pos_headwords": "lexicon/latin_glued_pos_headwords.py",
    "reference_index": "lexicon/reference_index.py",
    "text_encoding": "text/encoding.py"
}


@pytest.mark.parametrize("former, current", sorted(OWNERS.items()))
def test_no_root_shim_and_canonical_owner(former: str, current: str) -> None:
    assert not (PACKAGE / (former + ".py")).exists()
    assert (PACKAGE / current).is_file()
    assert importlib.util.find_spec("picture_capture." + former) is None
    module = "picture_capture." + current.removesuffix(".py").replace("/", ".")
    assert importlib.util.find_spec(module) is not None


def test_package_initializers_do_not_start_network_or_ocr() -> None:
    for package in ("lexicon", "text"):
        init = (PACKAGE / package / "__init__.py").read_text(encoding="utf-8")
        assert "from . import" not in init
        assert "urlopen(" not in init
        assert "PaddleOCR(" not in init


def test_lexical_public_helpers_resolve_without_legacy_root_imports() -> None:
    reference = importlib.import_module("picture_capture.lexicon.reference_index")
    collation = importlib.import_module("picture_capture.lexicon.collation")
    text = importlib.import_module("picture_capture.text.encoding")
    assert callable(reference.contains_cjk)
    assert callable(collation.collation_key)
    assert callable(text.decode_text_bytes)


def test_production_imports_use_canonical_lexicon_text_paths() -> None:
    """Statically include delayed imports; a GUI import must never use retired paths."""
    import ast

    forbidden = set(OWNERS)
    from itertools import chain

    all_python = chain(
        PACKAGE.rglob("*.py"),
        (PACKAGE.parents[1] / "tests").rglob("*.py"),
        (PACKAGE.parents[1] / "scripts").rglob("*.py"),
    )
    for path in all_python:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                name = node.module or ""
                if name in forbidden:
                    # Same-package relative imports are canonical, not retired.
                    permitted_internal = (
                        path.parent == PACKAGE / "lexicon"
                        and node.level == 1
                        and name in {"reference_index", "cc_cedict"}
                    )
                    assert permitted_internal, (path, node.lineno, name)
                assert not any(
                    name == "picture_capture." + old for old in forbidden
                ), (path, node.lineno, name)
                if name in {"picture_capture", ""}:
                    for imported in node.names:
                        assert imported.name not in forbidden, (
                            path, node.lineno, imported.name,
                        )
            elif isinstance(node, ast.Import):
                for imported in node.names:
                    assert imported.name not in {
                        "picture_capture." + old for old in forbidden
                    }, (path, node.lineno, imported.name)
