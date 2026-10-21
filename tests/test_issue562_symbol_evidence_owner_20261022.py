"""#562 physical Symbol Evidence owner: import path, source geometry, and marker authorization."""
from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.geometry.layout_transform import LayoutTransform
from picture_capture.layout import symbol_evidence as symbol
from picture_capture.models import Entry

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "picture_capture"


def test_symbol_evidence_physical_owner_no_root_module_and_importable():
    assert not (PACKAGE / "symbol_evidence.py").exists()
    assert (PACKAGE / "layout" / "symbol_evidence.py").is_file()
    assert importlib.util.find_spec("picture_capture.symbol_evidence") is None
    loaded = importlib.import_module("picture_capture.layout.symbol_evidence")
    assert loaded is symbol
    assert loaded.SymbolEvidenceResult.__module__ == loaded.__name__
    assert loaded.SymbolMarkerEvidence.__module__ == loaded.__name__


def test_symbol_marker_rescue_is_entry_only_bracket_cannot_create_entry():
    common = dict(
        column_index=0, literal="○", sample_id="profile-1",
        template_score=0.99, marker_x=9, marker_y=51,
        boundary_x=8, boundary_y=42, lane_x_ratio=0.6,
    )
    entry_marker = symbol.SymbolMarkerEvidence(role="entry_marker", **common)
    bracket = symbol.SymbolMarkerEvidence(role="bracket_open", **common)
    only_bracket = symbol.SymbolEvidenceResult(markers=[bracket])
    assert only_bracket.entry_candidates() == []
    assert len(only_bracket.bracket_openers) == 1
    only_entry = symbol.SymbolEvidenceResult(markers=[entry_marker])
    candidates = only_entry.entry_candidates()
    assert len(candidates) == 1
    assert isinstance(candidates[0], Entry)
    assert (candidates[0].x, candidates[0].y) == (8, 42)
    assert candidates[0].ocr_source == "symbol_evidence:entry_marker"
    assert "SYMBOL_ENTRY_MARKER_RESCUE" in candidates[0].issue_type


@pytest.mark.parametrize("kind", ["identity", "mirror_x", "rotate_ccw90", "rotate_cw90"])
def test_marker_boundary_remains_source_xy_after_layout_transform(kind):
    transform = LayoutTransform(kind)
    source_size = (140, 200)
    canonical_width, canonical_height = transform.canonical_size(source_size)
    line = SimpleNamespace(y0=18)
    column = SimpleNamespace(left=17, lines=[line])
    layout = SimpleNamespace(transform=transform, source_size=source_size, body_top=23)
    # Source coordinates must follow the same LayoutTransform as other Layout outputs.
    xy = symbol._marker_boundary_source(layout, column, line, 22.0)
    can_xy = transform.source_to_canonical_point(*xy, source_size)
    assert can_xy[0] == column.left
    assert 0 <= can_xy[1] < canonical_height
    assert 0 <= xy[0] < source_size[0]
    assert 0 <= xy[1] < source_size[1]


def test_no_retired_symbol_module_import_in_production_and_tests():
    for parent in (ROOT / "src", ROOT / "tests", ROOT / "scripts"):
        for source in parent.rglob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    assert not any(x.name == "picture_capture.symbol_evidence" for x in node.names), (source, node.lineno)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    assert module != "picture_capture.symbol_evidence", (source, node.lineno)
                    if module == "symbol_evidence" and node.level == 1:
                        assert "src/picture_capture/layout/" in source.as_posix(), (source, node.lineno)
                    if module == "picture_capture":
                        assert not any(a.name == "symbol_evidence" for a in node.names), (source, node.lineno)
