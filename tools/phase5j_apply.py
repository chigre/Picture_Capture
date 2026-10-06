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


# Retire the runtime installer but preserve both provenance transforms as normal,
# reusable diagnostic functions.  The corrected-indent function remains the
# underlying block producer, exactly matching the Phase 5I runtime order.
write(
    "src/picture_capture/layout_role_provenance.py",
    '''from __future__ import annotations\n\n"""Entry-source provenance helpers for Layout diagnostics."""\n\nfrom collections import Counter\nfrom typing import Any\n\nfrom .entry_classification import get_layout_line_classification\nfrom .layout_local_indent_visualization import drift_corrected_indent_blocks\n\n\ndef indent_blocks_with_entry_sources(understanding: Any) -> list[dict[str, Any]]:\n    """Return drift-corrected indent blocks annotated with entry provenance."""\n    blocks = list(drift_corrected_indent_blocks(understanding) or [])\n    layout = understanding.layout\n    body_top = int(getattr(layout, "body_top", 0) or 0)\n    source_by_key: dict[tuple[int, int, int], str] = {}\n    for column in list(getattr(layout, "columns", []) or []):\n        column_index = int(getattr(column, "index", 0) or 0)\n        for line in list(getattr(column, "lines", []) or []):\n            y0 = body_top + int(getattr(line, "y0", 0) or 0)\n            y1 = body_top + int(getattr(line, "y1", 0) or 0)\n            meta = get_layout_line_classification(line)\n            source_by_key[(column_index, y0, y1)] = str(\n                getattr(meta, "entry_source", "indent") or "indent"\n            )\n\n    for block in blocks:\n        try:\n            key = (\n                int(block.get("column", 0) or 0),\n                int(block["y0"]),\n                int(block["y1"]),\n            )\n        except (KeyError, TypeError, ValueError):\n            continue\n        role = str(block.get("role", "body") or "body").lower()\n        block["entry_source"] = (\n            source_by_key.get(key, "indent")\n            if role in {"entry", "headword"}\n            else "body"\n        )\n    return blocks\n\n\ndef add_entry_source_summary(base_text: str, app: Any) -> str:\n    """Insert the compact entry-source count line into a Layout summary."""\n    counts: Counter[str] = Counter()\n    for block in list(getattr(app, "_layout_visualization_indent_blocks", []) or []):\n        role = str(block.get("role", "body") or "body").lower()\n        if role not in {"entry", "headword"}:\n            continue\n        source = str(block.get("entry_source", "indent") or "indent")\n        counts[source] += 1\n    if not counts:\n        return base_text\n\n    order = ("indent", "large_head", "symbol_sample", "ocr", "manual", "unknown")\n    parts = [f"{name}={counts[name]}" for name in order if counts.get(name, 0)]\n    parts.extend(\n        f"{name}={count}"\n        for name, count in sorted(counts.items())\n        if name not in order\n    )\n    line = "entry sources: " + ", ".join(parts)\n    lines = base_text.splitlines()\n    insert_at = next(\n        (index + 1 for index, value in enumerate(lines) if value.startswith("line indents:")),\n        len(lines),\n    )\n    lines.insert(insert_at, line)\n    return "\\n".join(lines)\n\n\n__all__ = ["add_entry_source_summary", "indent_blocks_with_entry_sources"]\n''',
)
(ROOT / "src/picture_capture/layout_role_provenance_runtime.py").unlink()


# Shared visualization owns provenance-aware blocks statically.  The helper
# itself calls the same corrected-indent function that the old installer wrapped.
path = "src/picture_capture/layout_visualization_shared.py"
text = read(path)
text = replace_once(
    text,
    "from .layout_local_indent_visualization import drift_corrected_indent_blocks\n",
    "from .layout_role_provenance import indent_blocks_with_entry_sources\n",
    label="shared provenance import",
)
text = replace_once(
    text,
    "# The historical GUI installer assigned this exact function object before\n"
    "# role-provenance decorated it. Keep that ordering explicit at module load.\n"
    "_indent_blocks_from_understanding = drift_corrected_indent_blocks\n",
    "# Provenance now statically wraps the same drift-corrected block producer\n"
    "# that the historical GUI installer captured after Phase 5I.\n"
    "_indent_blocks_from_understanding = indent_blocks_with_entry_sources\n",
    label="shared provenance binding",
)
write(path, text)


# The base summary owns the provenance line before later role-theme, lane-summary
# and indent-visibility wrappers are installed.  This preserves the historical
# decorator nesting without any runtime replacement here.
path = "src/picture_capture/layout_visualization_summary.py"
text = read(path)
text = replace_once(
    text,
    "from .layout_visualization_readability import draw_layout_visualization_readable\n",
    "from .layout_role_provenance import add_entry_source_summary\n"
    "from .layout_visualization_readability import draw_layout_visualization_readable\n",
    label="summary provenance import",
)
# Limit replacement to the base formatter by splitting at the next function.
marker = "\n\ndef _summary_box("
head, tail = text.split(marker, 1)
head = replace_once(
    head,
    '    return "\\n".join(lines)\n',
    '    return add_entry_source_summary("\\n".join(lines), app)\n',
    label="base summary provenance",
)
write(path, head + marker + tail)


# GUI no longer installs provenance; later summary decorators keep their existing
# order and therefore continue wrapping the now-provenance-aware base formatter.
path = "src/picture_capture/bootstrap/gui.py"
text = read(path)
text = replace_once(
    text,
    "    from ..layout_role_provenance_runtime import install_layout_role_provenance\n",
    "",
    label="gui provenance import",
)
text = replace_once(
    text,
    "    install_shared_layout_visualization_source()\n"
    "    install_layout_role_provenance()\n"
    "    install_review_entry_classification(app_module)\n",
    "    install_shared_layout_visualization_source()\n"
    "    install_review_entry_classification(app_module)\n",
    label="gui provenance call",
)
write(path, text)


# Ratchet legacy runtime debt downward.
path = "scripts/architecture_guard.py"
text = read(path)
text = replace_once(
    text,
    '    "layout_role_provenance_runtime.py",\n',
    "",
    label="architecture provenance runtime",
)
write(path, text)


# Phase 5I/H source-shape checks should now assert static provenance ownership and
# preserve the later summary-wrapper ordering instead of requiring the installer.
path = "tests/test_layout_local_indent_visualization_runtime.py"
text = read(path)
text = replace_once(
    text,
    '    assert "_indent_blocks_from_understanding = drift_corrected_indent_blocks" in shared\n',
    '    assert "_indent_blocks_from_understanding = indent_blocks_with_entry_sources" in shared\n',
    label="phase5i static binding assertion",
)
text = replace_once(
    text,
    '    shared_pos = gui.index("install_shared_layout_visualization_source()")\n'
    '    provenance_pos = gui.index("install_layout_role_provenance()")\n'
    '    assert shared_pos < provenance_pos\n',
    '    assert "install_layout_role_provenance" not in gui\n'
    '    shared_pos = gui.index("install_shared_layout_visualization_source()")\n'
    '    role_theme_pos = gui.index("install_layout_role_theme()")\n'
    '    lane_pos = gui.index("install_physical_lane_summary()")\n'
    '    visibility_pos = gui.index("install_layout_indent_visibility()")\n'
    '    assert shared_pos < role_theme_pos < lane_pos < visibility_pos\n',
    label="phase5i provenance order assertion",
)
write(path, text)

path = "tests/test_layout_visualization_rows_capture.py"
text = read(path)
text = replace_once(
    text,
    '    shared_pos = gui.index("install_shared_layout_visualization_source()")\n'
    '    provenance_pos = gui.index("install_layout_role_provenance()")\n'
    '    assert shared_pos < provenance_pos\n',
    '    assert "install_layout_role_provenance" not in gui\n'
    '    shared_pos = gui.index("install_shared_layout_visualization_source()")\n'
    '    role_theme_pos = gui.index("install_layout_role_theme()")\n'
    '    assert shared_pos < role_theme_pos\n',
    label="phase5h provenance order assertion",
)
write(path, text)


# Focused behavior coverage for exact provenance matching, count ordering, fallback,
# and the static/later-wrapper architecture contract.
write(
    "tests/test_layout_role_provenance.py",
    '''from __future__ import annotations\n\nfrom pathlib import Path\nfrom types import SimpleNamespace\n\nimport picture_capture.layout_role_provenance as provenance\n\n\ndef test_indent_blocks_are_annotated_from_matching_layout_lines(monkeypatch):\n    entry_line = SimpleNamespace(y0=10, y1=20)\n    body_line = SimpleNamespace(y0=30, y1=40)\n    layout = SimpleNamespace(\n        body_top=100,\n        columns=[SimpleNamespace(index=2, lines=[entry_line, body_line])],\n    )\n    understanding = SimpleNamespace(layout=layout)\n    blocks = [\n        {"column": 2, "y0": 110, "y1": 120, "role": "entry"},\n        {"column": 2, "y0": 130, "y1": 140, "role": "body"},\n        {"column": 2, "y0": 150, "y1": 160, "role": "headword"},\n    ]\n\n    monkeypatch.setattr(\n        provenance, "drift_corrected_indent_blocks", lambda value: [dict(item) for item in blocks]\n    )\n    monkeypatch.setattr(\n        provenance,\n        "get_layout_line_classification",\n        lambda line: SimpleNamespace(entry_source="large_head" if line is entry_line else "ocr"),\n    )\n\n    result = provenance.indent_blocks_with_entry_sources(understanding)\n    assert result[0]["entry_source"] == "large_head"\n    assert result[1]["entry_source"] == "body"\n    # Unmatched entry/headword blocks retain the historical indent default.\n    assert result[2]["entry_source"] == "indent"\n\n\ndef test_entry_source_summary_inserts_after_line_indents_and_orders_sources():\n    app = SimpleNamespace(\n        _layout_visualization_indent_blocks=[\n            {"role": "entry", "entry_source": "custom_z"},\n            {"role": "entry", "entry_source": "manual"},\n            {"role": "headword", "entry_source": "large_head"},\n            {"role": "entry", "entry_source": "indent"},\n            {"role": "entry", "entry_source": "custom_a"},\n            {"role": "body", "entry_source": "ocr"},\n        ]\n    )\n    base = "Layout AUTO\\nline indents: 6   roles: x\\nrole strips: x"\n    text = provenance.add_entry_source_summary(base, app)\n    assert text.splitlines() == [\n        "Layout AUTO",\n        "line indents: 6   roles: x",\n        "entry sources: indent=1, large_head=1, manual=1, custom_a=1, custom_z=1",\n        "role strips: x",\n    ]\n\n\ndef test_entry_source_summary_returns_base_text_when_no_entry_counts():\n    app = SimpleNamespace(_layout_visualization_indent_blocks=[{"role": "body"}])\n    base = "Layout CURRENT\\nline indents: 1   roles: body"\n    assert provenance.add_entry_source_summary(base, app) == base\n\n\ndef test_phase5j_static_provenance_and_later_wrapper_order():\n    root = Path(__file__).resolve().parents[1]\n    package = root / "src" / "picture_capture"\n    gui = (package / "bootstrap" / "gui.py").read_text(encoding="utf-8")\n    shared = (package / "layout_visualization_shared.py").read_text(encoding="utf-8")\n    summary = (package / "layout_visualization_summary.py").read_text(encoding="utf-8")\n    guard = (root / "scripts" / "architecture_guard.py").read_text(encoding="utf-8")\n\n    assert not (package / "layout_role_provenance_runtime.py").exists()\n    assert (package / "layout_role_provenance.py").exists()\n    assert "_indent_blocks_from_understanding = indent_blocks_with_entry_sources" in shared\n    assert "add_entry_source_summary" in summary\n    assert "install_layout_role_provenance" not in gui\n    assert "layout_role_provenance_runtime.py" not in guard\n\n    shared_pos = gui.index("install_shared_layout_visualization_source()")\n    role_theme_pos = gui.index("install_layout_role_theme()")\n    lane_pos = gui.index("install_physical_lane_summary()")\n    visibility_pos = gui.index("install_layout_indent_visibility()")\n    assert shared_pos < role_theme_pos < lane_pos < visibility_pos\n''',
)

print("Phase 5J migration applied")
