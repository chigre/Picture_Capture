"""Transition guard for Phase 13E's already-migrated explicit consumers."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def _source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_migrated_physical_and_full_consumers_use_explicit_composition():
    core = _source("layout_core_understanding.py")
    processing = _source("processing.py")
    unlined = _source("unlined_physical_rows_resolver.py")
    assert "infer_composed_physical_page_layout as infer_dictionary_page_layout" in core
    assert "understanding = understand_composed_page(" in processing
    assert "understanding = page_understanding_module.understand_page(" not in processing
    assert "infer_composed_physical_page_layout(" in unlined
    assert "install_physical_indent_inference()" not in unlined


def test_explicit_full_service_has_isolated_raw_understanding_owner():
    full = _source("page_understanding.py")
    composed = _source("layout_composition.py")
    assert "_RAW_UNDERSTAND_PAGE = understand_page" in full
    assert "page_understanding._RAW_UNDERSTAND_PAGE(" in composed
    assert "normalize_layout_roles(understanding.layout)" in composed
