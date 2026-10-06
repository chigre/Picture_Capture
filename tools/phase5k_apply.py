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


# Preserve the display-only behavior in a normal module and expose the summary
# suffix as a pure helper so the existing lane-summary wrapper can remain the
# outer composition point.
write(
    "src/picture_capture/layout_indent_visibility.py",
    '''from __future__ import annotations\n\n"""Visible physical-indent rendering and prepared-count diagnostics."""\n\nfrom collections import Counter\nfrom typing import Any\n\n\n_FILL = "#fff59d"\n_EDGE = "#f9a825"\n\n\ndef prepared_indent_counts(blocks: list[dict[str, Any]]) -> dict[int, int]:\n    """Return 1-based per-column counts of drawable indent records."""\n    counts: Counter[int] = Counter()\n    for block in blocks:\n        try:\n            column = int(block.get("column", 0) or 0) + 1\n            x0 = float(block["x0"])\n            x1 = float(block["x1"])\n            y0 = int(block["y0"])\n            y1 = int(block["y1"])\n        except (KeyError, TypeError, ValueError):\n            continue\n        if abs(x1 - x0) < 1.0 or y1 <= y0:\n            continue\n        counts[column] += 1\n    return dict(sorted(counts.items()))\n\n\ndef _draw_indent_blocks_visible(app: Any, snapshot: Any) -> None:\n    """Draw each measured blank span above the page with a first-ink edge."""\n    from . import layout_visualization_summary as summary\n\n    canvas = getattr(app, "canvas", None)\n    if canvas is None:\n        return\n    indent_tag = summary._INDENT_TAG\n    try:\n        canvas.delete(indent_tag)\n    except Exception:\n        return\n\n    var = getattr(app, "_layout_visualization_var", None)\n    if var is None or not bool(var.get()):\n        return\n\n    geometry = snapshot.geometry\n    scale = float(getattr(app, "view_scale", 1.0) or 1.0)\n    blocks = list(getattr(app, "_layout_visualization_indent_blocks", []) or [])\n    app._layout_visualization_indent_prepared_counts = prepared_indent_counts(blocks)\n    if not blocks:\n        return\n\n    drawn: Counter[int] = Counter()\n    for block in blocks:\n        try:\n            column = int(block.get("column", 0) or 0) + 1\n            x0 = float(block["x0"])\n            x1 = float(block["x1"])\n            y0 = int(block["y0"])\n            y1 = int(block["y1"])\n        except (KeyError, TypeError, ValueError):\n            continue\n        if abs(x1 - x0) < 1.0 or y1 <= y0:\n            continue\n\n        try:\n            p0 = geometry.canonical_to_source(round(x0), y0)\n            p1 = geometry.canonical_to_source(round(x1), y1)\n        except Exception:\n            continue\n        left = min(float(p0[0]), float(p1[0])) * scale\n        right = max(float(p0[0]), float(p1[0])) * scale\n        top = min(float(p0[1]), float(p1[1])) * scale\n        bottom = max(float(p0[1]), float(p1[1])) * scale\n        if right - left < 1.0 or bottom - top < 1.0:\n            continue\n\n        try:\n            canvas.create_rectangle(\n                left,\n                top,\n                right,\n                bottom,\n                fill=_FILL,\n                outline=_EDGE,\n                width=1,\n                stipple="gray50",\n                tags=(indent_tag,),\n            )\n            canvas.create_line(\n                right,\n                top,\n                right,\n                bottom,\n                fill=_EDGE,\n                width=2,\n                tags=(indent_tag,),\n            )\n            drawn[column] += 1\n        except Exception:\n            continue\n\n    app._layout_visualization_indent_drawn_counts = dict(sorted(drawn.items()))\n    try:\n        canvas.tag_raise(indent_tag)\n    except Exception:\n        pass\n\n\ndef add_prepared_indent_summary(base_text: str, app: Any) -> str:\n    """Append the same outermost per-column prepared-indent diagnostic line."""\n    blocks = list(getattr(app, "_layout_visualization_indent_blocks", []) or [])\n    counts = prepared_indent_counts(blocks)\n    if counts:\n        detail = "   ".join(f"C{column}={count}" for column, count in counts.items())\n    else:\n        detail = "none"\n    return base_text + f"\\nindent blocks prepared: {detail}"\n\n\n__all__ = [\n    "_draw_indent_blocks_visible",\n    "add_prepared_indent_summary",\n    "prepared_indent_counts",\n]\n''',
)
(ROOT / "src/picture_capture/layout_indent_visibility_runtime.py").unlink()


# Static draw ownership: draw_layout_visualization_detailed resolves the summary
# module global at call time, so importing the visible renderer under the legacy
# private name preserves the historical runtime replacement without an installer.
path = "src/picture_capture/layout_visualization_summary.py"
text = read(path)
text = replace_once(
    text,
    "from .layout_role_provenance import add_entry_source_summary\n",
    "from .layout_indent_visibility import _draw_indent_blocks_visible as _draw_indent_blocks\n"
    "from .layout_role_provenance import add_entry_source_summary\n",
    label="summary visible renderer import",
)
start = text.index("def _draw_indent_blocks(app: Any, snapshot: Any) -> None:")
end = text.index("\n\ndef _draw_role_strips", start)
text = text[:start] + text[end + 2:]
write(path, text)


# Preserve the old outermost text order.  Historically the visibility runtime
# wrapped the already-installed physical-lane formatter.  With the runtime gone,
# the lane wrapper performs the same two transforms in the same order.
path = "src/picture_capture/layout_lane_summary_extension.py"
text = read(path)
text = replace_once(
    text,
    "from typing import Any, Callable\n",
    "from typing import Any, Callable\n\n"
    "from .layout_indent_visibility import add_prepared_indent_summary\n",
    label="lane prepared-summary import",
)
text = replace_once(
    text,
    "    def wrapped(app: Any, snapshot: Any) -> str:\n"
    "        return append_physical_lane_summary(original(app, snapshot), app)\n",
    "    def wrapped(app: Any, snapshot: Any) -> str:\n"
    "        text = append_physical_lane_summary(original(app, snapshot), app)\n"
    "        return add_prepared_indent_summary(text, app)\n",
    label="lane outer prepared summary",
)
write(path, text)


# GUI composition no longer needs the visibility installer.  The physical-lane
# installer remains at the same position and now owns the final prepared suffix.
path = "src/picture_capture/bootstrap/gui.py"
text = read(path)
text = replace_once(
    text,
    "    from ..layout_indent_visibility_runtime import install_layout_indent_visibility\n",
    "",
    label="gui visibility import",
)
text = replace_once(
    text,
    "    install_physical_lane_summary()\n"
    "    # Install after the final Layout summary wrappers so both C1/C2 prepared\n"
    "    # indent spans stay visible and the per-column block counts are reported.\n"
    "    install_layout_indent_visibility()\n",
    "    # The lane-summary wrapper now appends the prepared-indent diagnostic as\n"
    "    # its final step; visible indent drawing is static in the summary module.\n"
    "    install_physical_lane_summary()\n",
    label="gui visibility call",
)
write(path, text)


# Ratchet legacy runtime debt downward.
path = "scripts/architecture_guard.py"
text = read(path)
text = replace_once(
    text,
    '    "layout_indent_visibility_runtime.py",\n',
    "",
    label="architecture visibility runtime",
)
write(path, text)


# Migrate the dedicated behavior/source-shape tests to the non-runtime owner and
# add an integration regression for the lane -> prepared summary ordering.
path = "tests/test_layout_indent_visibility_runtime.py"
text = read(path)
text = replace_once(
    text,
    "from picture_capture.layout_indent_visibility_runtime import (\n"
    "    _draw_indent_blocks_visible,\n"
    "    prepared_indent_counts,\n"
    ")\n",
    "from picture_capture.layout_indent_visibility import (\n"
    "    _draw_indent_blocks_visible,\n"
    "    add_prepared_indent_summary,\n"
    "    prepared_indent_counts,\n"
    ")\n",
    label="visibility test import",
)
start = text.index("def test_gui_composition_installs_indent_visibility_after_lane_summary():")
end = text.index("\n\ndef test_visibility_runtime_does_not_lower_indent_below_base_layout", start)
replacement = '''def test_static_visibility_preserves_lane_then_prepared_summary_order(monkeypatch):\n    from picture_capture import layout_lane_summary_extension as lane\n    from picture_capture import layout_visualization_summary as summary\n\n    app = SimpleNamespace(\n        _layout_visualization_indent_lanes=[\n            {\n                "column": 0,\n                "lane": 0,\n                "center": 12.0,\n                "min": 10.0,\n                "max": 14.0,\n                "raw_min": 11.0,\n                "raw_max": 15.0,\n                "support": 3,\n                "role": "entry",\n            }\n        ],\n        _layout_visualization_indent_blocks=[_block(0, 60, 120, 100, 130)],\n    )\n    monkeypatch.setattr(summary, "_format_summary", lambda _app, _snapshot: "base")\n    monkeypatch.setattr(summary, "_physical_lane_summary_installed", False, raising=False)\n\n    lane.install_physical_lane_summary()\n    output = summary._format_summary(app, SimpleNamespace())\n    assert output.index("physical indent lanes:") < output.index("indent blocks prepared: C1=1")\n\n\ndef test_phase5k_static_visibility_ownership():\n    root = Path(__file__).resolve().parents[1]\n    package = root / "src" / "picture_capture"\n    gui = (package / "bootstrap" / "gui.py").read_text(encoding="utf-8")\n    summary = (package / "layout_visualization_summary.py").read_text(encoding="utf-8")\n    lane = (package / "layout_lane_summary_extension.py").read_text(encoding="utf-8")\n    guard = (root / "scripts" / "architecture_guard.py").read_text(encoding="utf-8")\n\n    assert not (package / "layout_indent_visibility_runtime.py").exists()\n    assert (package / "layout_indent_visibility.py").exists()\n    assert "_draw_indent_blocks_visible as _draw_indent_blocks" in summary\n    assert "add_prepared_indent_summary(text, app)" in lane\n    assert "install_layout_indent_visibility" not in gui\n    assert "layout_indent_visibility_runtime.py" not in guard\n'''
text = text[:start] + replacement + text[end + 2:]
text = text.replace(
    '        / "layout_indent_visibility_runtime.py"\n',
    '        / "layout_indent_visibility.py"\n',
)
text = text.replace(
    "def test_visibility_runtime_does_not_lower_indent_below_base_layout():",
    "def test_visible_renderer_does_not_lower_indent_below_base_layout():",
)
text += '''\n\ndef test_prepared_summary_none_fallback():\n    app = SimpleNamespace(_layout_visualization_indent_blocks=[])\n    assert add_prepared_indent_summary("base", app) == "base\\nindent blocks prepared: none"\n'''
write(path, text)


# Earlier architecture guards should now stop expecting the retired installer,
# while retaining shared -> role theme -> lane composition ordering.
for path in (
    "tests/test_layout_role_provenance.py",
    "tests/test_layout_local_indent_visualization_runtime.py",
):
    text = read(path)
    text = replace_once(
        text,
        '    visibility_pos = gui.index("install_layout_indent_visibility()")\n'
        '    assert shared_pos < role_theme_pos < lane_pos < visibility_pos\n',
        '    assert "install_layout_indent_visibility" not in gui\n'
        '    assert shared_pos < role_theme_pos < lane_pos\n',
        label=f"{path} visibility order assertion",
    )
    write(path, text)

print("Phase 5K migration applied")
