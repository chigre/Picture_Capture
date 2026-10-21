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
