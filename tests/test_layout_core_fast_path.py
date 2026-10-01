from __future__ import annotations

from pathlib import Path


def test_processing_routes_ordinary_to_layout_only_fast_path() -> None:
    source = Path("src/picture_capture/processing.py").read_text(encoding="utf-8")
    assert "ordinary_mode = method not in" in source
    assert "layout_only=ordinary_mode" in source
    assert "from .layout_core_understanding import understand_layout_core" in source


def test_layout_visualization_uses_layout_only_fast_path() -> None:
    source = Path("src/picture_capture/layout_visualization_shared.py").read_text(
        encoding="utf-8"
    )
    assert "layout_only=True" in source
    assert "method = \"layout_core\"" in source


def test_layout_core_skips_semantic_and_symbol_work() -> None:
    source = Path("src/picture_capture/layout_core_understanding.py").read_text(
        encoding="utf-8"
    )
    assert "detect_symbol_evidence(" not in source
    assert "refine_indent_semantics(" not in source
    assert "_guard_band_entries(" not in source
    assert "refine_boundaries_toward_head_top(" not in source
    assert "semantic_reliable=False" in source
    assert "SymbolEvidenceResult(markers=[])" in source


def test_layout_core_and_auto_layout_have_bounded_caches() -> None:
    core = Path("src/picture_capture/layout_core_understanding.py").read_text(
        encoding="utf-8"
    )
    detector = Path("src/picture_capture/layout_detection.py").read_text(
        encoding="utf-8"
    )
    assert "_CACHE_LIMIT = 6" in core
    assert "_LAYOUT_CACHE" in core
    assert "popitem(last=False)" in core
    assert "_LAYOUT_ESTIMATE_CACHE_LIMIT = 8" in detector
    assert "_LAYOUT_ESTIMATE_CACHE" in detector
    assert "popitem(last=False)" in detector
