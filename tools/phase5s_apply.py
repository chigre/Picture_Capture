from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    source = read(path)
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one replacement, found {count}")
    write(path, source.replace(old, new, 1))


# Move deterministic column-drift behavior out of the runtime-named module.
runtime_path = ROOT / "src/picture_capture/layout_column_drift_runtime.py"
helper_path = ROOT / "src/picture_capture/layout_column_drift.py"
if helper_path.exists():
    raise RuntimeError("layout_column_drift.py already exists")
runtime_path.rename(helper_path)

helper = helper_path.read_text(encoding="utf-8")
helper = helper.replace(
    "from typing import Any, Callable\n",
    "from typing import Any\n",
    1,
)
helper = helper.replace(
    "This runtime keeps the configured column geometry unchanged but re-measures each\n",
    "This helper keeps the configured column geometry unchanged but re-measures each\n",
    1,
)
helper = helper.replace(
    "            # Runtime installers already replace these with the physical-indent\n"
    "            # implementations. Rebuild modes and roles from the unclipped values.\n",
    "            # Composition already provides the physical-indent implementations.\n"
    "            # Rebuild modes and roles from the unclipped values.\n",
    1,
)
start = helper.index("def _remeasure_policy_layout(")
helper = helper[:start] + '''def finalize_layout_column_drift(
    image: Image.Image,
    settings: Any,
    layout: Any,
    *,
    page_index: int = 0,
) -> Any:
    """Apply the historical post-policy indent remeasurement without monkey patching."""
    from . import dictionary_page_design as base
    from .layout_detection import analysis_ink_mask

    source, canonical, _transform, effective = base._analysis_page(
        image,
        settings,
        int(page_index),
    )
    try:
        page_ink = analysis_ink_mask(
            np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8),
            effective,
        )
        counts = remeasure_layout_indents_from_ink(layout, page_ink)
    finally:
        try:
            canonical.close()
        except Exception:
            pass
        try:
            source.close()
        except Exception:
            pass

    if counts:
        detail = ",".join(
            f"C{index + 1}:{count}" for index, count in sorted(counts.items())
        )
        layout.reason += f"; unclipped_first_x={detail}"
    return layout


__all__ = [
    "_analysis_left_for_column",
    "_left_safety",
    "finalize_layout_column_drift",
    "remeasure_layout_indents_from_ink",
]
'''
helper_path.write_text(helper, encoding="utf-8")

# Make post-policy column-drift finalization explicit and static.
replace_once(
    "src/picture_capture/dictionary_page_layout_policy.py",
    "from .layout_detection import analysis_ink_mask, detect_layout_parameters, LayoutEstimate\n",
    "from .layout_detection import analysis_ink_mask, detect_layout_parameters, LayoutEstimate\n"
    "from .layout_column_drift import finalize_layout_column_drift\n",
)
replace_once(
    "src/picture_capture/dictionary_page_layout_policy.py",
    "    return layout, page_settings, applied\n\n\ndef detect_entries_from_page_design",
    "    layout = finalize_layout_column_drift(\n"
    "        image,\n"
    "        page_settings,\n"
    "        layout,\n"
    "        page_index=int(page_index),\n"
    "    )\n"
    "    return layout, page_settings, applied\n\n\ndef detect_entries_from_page_design",
)

# Large-head evidence keeps the exact same shared left-safety helper, now from
# ordinary non-runtime ownership.
replace_once(
    "src/picture_capture/ordinary_large_head_runtime.py",
    "from .layout_column_drift_runtime import _analysis_left_for_column",
    "from .layout_column_drift import _analysis_left_for_column",
)
replace_once(
    "src/picture_capture/ordinary_large_head_runtime.py",
    "Layout column-drift runtime's analysis-only left\n",
    "Layout column-drift helper's analysis-only left\n",
)

# GUI no longer needs to install column drift before policy imports.
replace_once(
    "src/picture_capture/bootstrap/gui.py",
    "    from ..layout_physical_indent import install_physical_indent_inference\n"
    "    from ..layout_column_drift_runtime import install_layout_column_drift_runtime\n",
    "    from ..layout_physical_indent import install_physical_indent_inference\n",
)
replace_once(
    "src/picture_capture/bootstrap/gui.py",
    "    # Long-band logical row recovery is now static in layout_physical_indent.\n"
    "    # Keep semantic column geometry fixed while allowing analysis pixels to\n"
    "    # extend left of it on slanted/curved scans. This must be ready before the\n"
    "    # shared Layout Core imports policy/large-head callables by value.\n"
    "    install_layout_column_drift_runtime()\n",
    "    # Long-band row recovery and column-drift indent remeasurement are now\n"
    "    # static; only the remaining physical-indent installer needs ordering.\n",
)

# Worker composition likewise stops installing column drift.
replace_once(
    "src/picture_capture/bootstrap/worker.py",
    "    from ..layout_column_drift_runtime import install_layout_column_drift_runtime\n",
    "",
)
replace_once(
    "src/picture_capture/bootstrap/worker.py",
    "    # Long-band row recovery is static in layout_physical_indent. Column drift\n"
    "    # remains an explicit process-local runtime until its own slice is proven.\n"
    "    install_layout_column_drift_runtime()\n",
    "    # Long-band row recovery and column-drift remeasurement are static.\n",
)

# The unlined escalation path still prepares physical-indent dependencies but no
# longer requires a column-drift installer before importing policy.
replace_once(
    "src/picture_capture/unlined_physical_rows_resolver.py",
    "    # Escalate geometry only. Character-height fallback is static in the\n"
    "    # detector; the remaining installers are still required because an\n"
    "    # unlined worker is spawned independently of the GUI launcher.\n"
    "    from .layout_column_drift_runtime import install_layout_column_drift_runtime\n",
    "    # Escalate geometry only. Character-height fallback and column-drift\n"
    "    # remeasurement are static; the remaining installers are still required\n"
    "    # because an unlined worker is spawned independently of the GUI launcher.\n",
)
replace_once(
    "src/picture_capture/unlined_physical_rows_resolver.py",
    "    # Long-band row recovery is already static in layout_physical_indent.\n"
    "    install_layout_column_drift_runtime()\n",
    "    # Long-band row recovery is already static in layout_physical_indent.\n",
)

# Keep the spawn-layout adapter as its own later seam, but remove the now-obsolete
# column-drift extension from its wrapper.
write(
    "src/picture_capture/spawn_layout_runtime.py",
    '''from __future__ import annotations

"""Keep the remaining Page/Layout runtime preparation identical in workers.

``processing._understand_page_current`` calls ``_ensure_layout_runtime`` inside
ordinary-drawing workers. Long-band row recovery and column-drift indent
remeasurement are now static. The helper still prepares robust line starts and
physical-indent behavior through the historical processing entry point.

This compatibility adapter remains a separate spawn-runtime seam so its final
retirement can be proven independently rather than bundled into Phase 5S.
"""

from functools import wraps
from typing import Any


def install_spawn_layout_runtime(processing_module: Any) -> None:
    """Retain the idempotent worker entry wrapper without column-drift patching."""
    if bool(getattr(processing_module, "_pc_spawn_layout_runtime_installed", False)):
        return

    original = processing_module._ensure_layout_runtime

    @wraps(original)
    def ensure_layout_runtime() -> None:
        original()

    processing_module._ensure_layout_runtime = ensure_layout_runtime
    processing_module._pc_spawn_layout_runtime_installed = True


__all__ = ["install_spawn_layout_runtime"]
''',
)

# Ratchet legacy runtime debt.
replace_once(
    "scripts/architecture_guard.py",
    '    "layout_column_drift_runtime.py",\n',
    "",
)

# Focused characterization now targets static ownership while preserving all
# previous drift and large-head contracts.
write(
    "tests/test_layout_column_drift_runtime.py",
    '''from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from picture_capture import dictionary_page_design as base
from picture_capture import layout_detection
from picture_capture.dictionary_page_design import LayoutLine
from picture_capture.layout_column_drift import (
    _analysis_left_for_column,
    _left_safety,
    finalize_layout_column_drift,
    remeasure_layout_indents_from_ink,
)
from picture_capture.layout_transform import LayoutTransform
from picture_capture.ordinary_large_head_runtime import (
    detect_ordinary_large_head_entries_guarded,
)


def _line(y0: int, y1: int, *, first_x: int = 0) -> LayoutLine:
    return LayoutLine(
        column=0,
        y0=y0,
        y1=y1,
        first_x=first_x,
        anchor_x=None,
        anchor_width=0,
        anchor_height=0,
        gap_before=0,
        patch=np.zeros((0, 0), dtype=bool),
    )


def test_remeasurement_keeps_negative_first_x_instead_of_clipping_to_zero():
    ink = np.zeros((100, 180), dtype=bool)
    ink[10:25, 45:51] = True
    ink[45:60, 39:45] = True

    lines = [_line(10, 25), _line(45, 60)]
    column = SimpleNamespace(
        index=0,
        left=50,
        right=150,
        lines=lines,
        indent_modes=[],
        body_mode=None,
        entry_modes=[],
    )
    layout = SimpleNamespace(
        body_top=0,
        ordinary_line_height=20.0,
        indent_type="body",
        columns=[column],
    )

    counts = remeasure_layout_indents_from_ink(layout, ink)

    assert counts == {0: 2}
    assert lines[0].first_x == -5
    assert lines[1].first_x == -11
    assert column.left == 50
    assert column.right == 150


def test_left_safety_is_large_enough_for_scan_drift_but_bounded():
    assert _left_safety(20.0, 1000) >= 30
    assert _left_safety(40.0, 1000) >= 60
    assert _left_safety(80.0, 1000) <= 96


def test_later_column_analysis_never_crosses_previous_text_column():
    columns = [
        SimpleNamespace(left=50, right=150),
        SimpleNamespace(left=170, right=270),
    ]
    analysis_left = _analysis_left_for_column(columns, 1, 40.0)
    assert 151 <= analysis_left < 170
    assert columns[1].left == 170


def test_static_finalizer_replays_analysis_and_preserves_reason_provenance(monkeypatch):
    image = Image.new("RGB", (180, 100), "white")
    ink = np.zeros((100, 180), dtype=bool)
    ink[10:25, 45:51] = True
    ink[45:60, 39:45] = True

    lines = [_line(10, 25), _line(45, 60)]
    column = SimpleNamespace(
        index=0,
        left=50,
        right=150,
        lines=lines,
        indent_modes=[],
        body_mode=None,
        entry_modes=[],
    )
    layout = SimpleNamespace(
        body_top=0,
        ordinary_line_height=20.0,
        indent_type="body",
        columns=[column],
        reason="base",
    )
    settings = SimpleNamespace()
    calls: list[int] = []

    def fake_analysis_page(source_image, page_settings, page_index):
        calls.append(int(page_index))
        return source_image.copy(), source_image.copy(), None, page_settings

    monkeypatch.setattr(base, "_analysis_page", fake_analysis_page)
    monkeypatch.setattr(
        layout_detection,
        "analysis_ink_mask",
        lambda _gray, _settings: ink,
    )

    result = finalize_layout_column_drift(
        image,
        settings,
        layout,
        page_index=3,
    )

    assert result is layout
    assert calls == [3]
    assert lines[0].first_x == -5
    assert lines[1].first_x == -11
    assert layout.reason == "base; unclipped_first_x=C1:2"
    assert column.left == 50
    assert column.right == 150


def test_large_head_left_of_semantic_column_is_still_detected():
    image = Image.new("RGB", (220, 180), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((38, 24, 68, 74), fill="black")

    row = _line(24, 75, first_x=-12)
    column = SimpleNamespace(index=0, left=50, right=170, lines=[row])
    layout = SimpleNamespace(
        transform=LayoutTransform(),
        source_size=image.size,
        body_top=0,
        body_bottom=160,
        ordinary_line_height=20.0,
        columns=[column],
    )
    understanding = SimpleNamespace(layout=layout)
    settings = SimpleNamespace(
        profile_cjk_allow_single_headword=True,
        dictionary_profile_id="cjk-test",
        ocr_language="chi_sim",
        paddle_language="ch",
    )

    entries = detect_ordinary_large_head_entries_guarded(
        image, understanding, settings,
    )

    assert entries
    assert any(entry.ocr_oversized_cjk for entry in entries)
    assert min(entry.y for entry in entries) <= 30
    assert all(entry.x == 50 for entry in entries)


def test_column_drift_is_static_and_shared_helper_ownership_is_explicit():
    root = Path(__file__).resolve().parents[1]
    core = (root / "src/picture_capture/bootstrap/core.py").read_text(encoding="utf-8")
    gui = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")
    worker = (root / "src/picture_capture/bootstrap/worker.py").read_text(encoding="utf-8")
    policy = (root / "src/picture_capture/dictionary_page_layout_policy.py").read_text(encoding="utf-8")
    unlined = (root / "src/picture_capture/unlined_physical_rows_resolver.py").read_text(encoding="utf-8")
    spawn = (root / "src/picture_capture/spawn_layout_runtime.py").read_text(encoding="utf-8")
    large_head = (root / "src/picture_capture/ordinary_large_head_runtime.py").read_text(encoding="utf-8")
    physical = (root / "src/picture_capture/layout_physical_indent.py").read_text(encoding="utf-8")

    assert core.index("install_ordinary_large_head_role_guard()") < core.index(
        "from .. import processing as processing_module"
    )
    assert "from .layout_column_drift import finalize_layout_column_drift" in policy
    layout_at = policy.index("layout = base.DictionaryPageLayout(")
    finalize_at = policy.index("layout = finalize_layout_column_drift(")
    return_at = policy.index("return layout, page_settings, applied", finalize_at)
    assert layout_at < finalize_at < return_at

    for source in (gui, worker, unlined, spawn, policy):
        assert "install_layout_column_drift_runtime" not in source
    assert "from .layout_column_drift import _analysis_left_for_column" in large_head
    assert "layout_column_drift_runtime" not in large_head
    assert "count = min(256, count)" in physical
''',
)

write(
    "tests/test_spawn_layout_runtime.py",
    '''from __future__ import annotations

from pathlib import Path


def test_core_composition_keeps_worker_layout_preparation_without_column_drift_patch():
    from picture_capture.bootstrap.core import build_core_services

    services = build_core_services()
    processing = services.processing
    from picture_capture import dictionary_page_layout_policy as policy
    from picture_capture import layout_physical_indent as physical

    assert bool(getattr(processing, "_pc_spawn_layout_runtime_installed", False))
    assert not bool(getattr(policy, "_column_drift_runtime_installed", False))

    static_helper = physical._logical_slots_for_oversized_run
    slots = static_helper(0, 400, 40.0)
    first = processing._ensure_layout_runtime
    processing._ensure_layout_runtime()

    assert processing._ensure_layout_runtime is first
    assert physical._logical_slots_for_oversized_run is static_helper
    assert len(slots) == 10

    policy_source = (
        Path(__file__).resolve().parents[1]
        / "src/picture_capture/dictionary_page_layout_policy.py"
    ).read_text(encoding="utf-8")
    assert "finalize_layout_column_drift(" in policy_source


def test_spawn_layout_runtime_is_idempotent():
    from picture_capture.bootstrap.core import build_core_services

    processing = build_core_services().processing
    first = processing._ensure_layout_runtime
    processing._ensure_layout_runtime()
    processing._ensure_layout_runtime()
    assert processing._ensure_layout_runtime is first
''',
)

replace_once(
    "tests/test_runtime_entry_path_guards.py",
    '    assert "install_layout_column_drift_runtime()" in worker\n',
    '    assert "install_layout_column_drift_runtime()" not in worker\n'
    '    policy = (\n'
    '        root / "src" / "picture_capture" / "dictionary_page_layout_policy.py"\n'
    '    ).read_text(encoding="utf-8")\n'
    '    assert "finalize_layout_column_drift(" in policy\n',
)

print("Phase 5S migration applied")
