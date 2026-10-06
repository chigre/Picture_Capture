from __future__ import annotations

from pathlib import Path


path = Path("tools/phase5r_apply.py")
text = path.read_text(encoding="utf-8")
old = '''def replace_once(rel: str, old: str, new: str) -> None:\n    text = read(rel)\n    count = text.count(old)\n    if count != 1:\n        raise RuntimeError(f"{rel}: expected exactly one migration anchor, found {count}")\n    write(rel, text.replace(old, new, 1))\n'''
new = '''def replace_once(rel: str, old: str, new: str) -> None:\n    text = read(rel)\n    count = text.count(old)\n    if count == 0:\n        # Some generated multi-line anchors are dedented for readable helper\n        # source even though the real block lives one function-indent inward.\n        # Accept that exact four-space shape only; all other mismatches fail.\n        indented_old = "".join(\n            ("    " + line) if line.strip() else line\n            for line in old.splitlines(keepends=True)\n        )\n        indented_new = "".join(\n            ("    " + line) if line.strip() else line\n            for line in new.splitlines(keepends=True)\n        )\n        if text.count(indented_old) == 1:\n            write(rel, text.replace(indented_old, indented_new, 1))\n            return\n    if count != 1:\n        raise RuntimeError(f"{rel}: expected exactly one migration anchor, found {count}")\n    write(rel, text.replace(old, new, 1))\n'''
if text.count(old) != 1:
    raise RuntimeError("phase5r replace_once definition drifted")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Phase 5R migration helper prepared with indentation-safe anchors")
