"""Issue #562: fifteen physically relocated evidence owners and canonical imports."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
MOVED = {
        "ordinary_bracket_pair": "ordinary/bracket_pair.py",
        "ordinary_cpu_pool": "ordinary/cpu_pool.py",
        "ordinary_evidence_fusion": "ordinary/evidence_fusion.py",
        "ordinary_gpu_pipeline": "ordinary/gpu_pipeline.py",
        "ordinary_indent_topology": "ordinary/indent_topology.py",
        "ordinary_large_head_evidence": "ordinary/large_head_evidence.py",
        "ordinary_large_head_role_guard": "ordinary/large_head_role_guard.py",
        "ordinary_parallel": "ordinary/parallel.py",
        "ordinary_visual": "ordinary/visual.py",
        "entry_ocr_crop": "ocr/entry_crop.py",
        "entry_ocr_visual_scale": "ocr/entry_visual_scale.py",
        "page_understanding": "layout/page_understanding.py",
        "page_understanding_fusion": "layout/page_understanding_fusion.py",
        "large_head_visual_diagnostics": "ordinary/large_head_visual_diagnostics.py",
        "layout_visualization_role_theme": "layout/visualization_role_theme.py",
}

def test_evidence_batch15_physical_owners():
    for former, owner in MOVED.items():
        assert not (ROOT / (former + ".py")).exists(), former
        assert (ROOT / owner).is_file(), owner

def test_no_static_or_direct_dynamic_obsolete_evidence_imports():
    removed = set(MOVED)
    bad = []
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split(".")
                    if len(parts) > 1 and parts[0] == "picture_capture" and parts[1] in removed:
                        bad.append((str(path), node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parent = path.parent.relative_to(ROOT).parts
                    up = len(parent) + 1 - node.level
                    parts = (*parent[:max(up, 0)], *(node.module or "").split("."))
                else:
                    name = (node.module or "").split(".")
                    parts = tuple(name[1:] if name and name[0] == "picture_capture" else name)
                if parts and parts[0] in removed:
                    bad.append((str(path), node.lineno, node.module))
                if node.module in (None, "picture_capture") and any(a.name in removed for a in node.names):
                    bad.append((str(path), node.lineno, "from-root obsolete"))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in {"picture_capture." + old for old in removed}:
                    bad.append((str(path), node.lineno, node.value))
    assert not bad, bad[:40]
