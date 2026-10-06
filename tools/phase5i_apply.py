from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


# Preserve the proven pure corrected-indent function in a non-runtime module.
old_path = ROOT / "src/picture_capture/layout_local_indent_visualization_runtime.py"
old = old_path.read_text(encoding="utf-8")
start = old.index("def drift_corrected_indent_blocks(")
end = old.index("\n\ndef install_local_indent_visualization", start)
func = old[start:end].rstrip() + "\n"
new_module = '''from __future__ import annotations\n\n\"\"\"Drift-corrected physical indent blocks used by Layout diagnostics.\"\"\"\n\nfrom typing import Any\n\nfrom .layout_physical_indent import normalized_physical_indents\n\n\n''' + func + '\n\n__all__ = ["drift_corrected_indent_blocks"]\n'
write("src/picture_capture/layout_local_indent_visualization.py", new_module)
old_path.unlink()


# Static ownership: shared visualization binds the exact function object that the
# historical installer installed before role-provenance wrapped it.
path = "src/picture_capture/layout_visualization_shared.py"
text = read(path)
text = replace_once(
    text,
    "from .layout_physical_indent import normalized_physical_indents\n",
    "from .layout_local_indent_visualization import drift_corrected_indent_blocks\n"
    "from .layout_physical_indent import normalized_physical_indents\n",
    label="shared local-indent import",
)
start = text.index("def _indent_blocks_from_understanding(")
end = text.index("\n\ndef _indent_lanes_from_understanding", start)
text = (
    text[:start]
    + "# The historical GUI installer assigned this exact function object before\n"
      "# role-provenance decorated it. Keep that ordering explicit at module load.\n"
      "_indent_blocks_from_understanding = drift_corrected_indent_blocks\n"
    + text[end:]
)
write(path, text)


# GUI composition no longer needs the local-indent replacement installer. Keep
# shared publication followed by role-provenance decoration.
path = "src/picture_capture/bootstrap/gui.py"
text = read(path)
text = replace_once(
    text,
    "    from ..layout_local_indent_visualization_runtime import install_local_indent_visualization\n",
    "",
    label="gui local-indent import",
)
text = replace_once(
    text,
    "    install_shared_layout_visualization_source()\n"
    "    install_local_indent_visualization()\n"
    "    install_layout_role_provenance()\n",
    "    install_shared_layout_visualization_source()\n"
    "    install_layout_role_provenance()\n",
    label="gui local-indent call",
)
write(path, text)


# Ratchet the retired runtime filename out of the architecture debt baseline.
path = "scripts/architecture_guard.py"
text = read(path)
text = replace_once(
    text,
    '    "layout_local_indent_visualization_runtime.py",\n',
    "",
    label="architecture local-indent runtime",
)
write(path, text)


# Keep the existing behavior test but point it to the non-runtime owner, and add
# source/order assertions for static shared ownership and later provenance wrap.
path = "tests/test_layout_local_indent_visualization_runtime.py"
text = read(path)
text = replace_once(
    text,
    "from picture_capture.layout_local_indent_visualization_runtime import (\n"
    "    drift_corrected_indent_blocks,\n"
    ")\n",
    "from picture_capture.layout_local_indent_visualization import (\n"
    "    drift_corrected_indent_blocks,\n"
    ")\n",
    label="local-indent test import",
)
text = replace_once(
    text,
    '        "picture_capture.layout_local_indent_visualization_runtime.normalized_physical_indents",\n',
    '        "picture_capture.layout_local_indent_visualization.normalized_physical_indents",\n',
    label="local-indent test monkeypatch",
)
text += '''\n\ndef test_phase5i_static_owner_and_provenance_order():\n    from pathlib import Path\n\n    root = Path(__file__).resolve().parents[1]\n    package = root / "src" / "picture_capture"\n    shared = (package / "layout_visualization_shared.py").read_text(encoding="utf-8")\n    gui = (package / "bootstrap" / "gui.py").read_text(encoding="utf-8")\n    guard = (root / "scripts" / "architecture_guard.py").read_text(encoding="utf-8")\n\n    assert not (package / "layout_local_indent_visualization_runtime.py").exists()\n    assert (package / "layout_local_indent_visualization.py").exists()\n    assert "_indent_blocks_from_understanding = drift_corrected_indent_blocks" in shared\n    assert "install_local_indent_visualization" not in gui\n    assert "layout_local_indent_visualization_runtime.py" not in guard\n    shared_pos = gui.index("install_shared_layout_visualization_source()")\n    provenance_pos = gui.index("install_layout_role_provenance()")\n    assert shared_pos < provenance_pos\n'''
write(path, text)

print("Phase 5I migration applied")
