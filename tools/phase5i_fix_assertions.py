from __future__ import annotations

from pathlib import Path

path = Path(__file__).resolve().parents[1] / "tests/test_layout_visualization_rows_capture.py"
text = path.read_text(encoding="utf-8")
old = '''    shared_pos = gui.index("install_shared_layout_visualization_source()")\n    local_pos = gui.index("install_local_indent_visualization()")\n    provenance_pos = gui.index("install_layout_role_provenance()")\n    assert shared_pos < local_pos < provenance_pos\n'''
new = '''    assert "install_local_indent_visualization" not in gui\n    shared_pos = gui.index("install_shared_layout_visualization_source()")\n    provenance_pos = gui.index("install_layout_role_provenance()")\n    assert shared_pos < provenance_pos\n'''
if text.count(old) != 1:
    raise SystemExit(f"stale Phase 5H order assertion: expected one match, got {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Phase 5I stale ownership assertion migrated")
