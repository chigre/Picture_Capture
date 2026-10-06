from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if text.count(start) != 1 or text.count(end) < 1:
        raise SystemExit(f"{path}: migration markers are not unique/present")
    left = text.index(start)
    right = text.index(end, left)
    target.write_text(text[:left] + replacement + text[right:], encoding="utf-8")


# 1. Make the already-characterized long-band fallback ordinary static code.
replace_once(
    "src/picture_capture/layout_physical_indent.py",
    "from typing import Any, Callable\n",
    "import math\nfrom typing import Any, Callable\n",
)
replace_between(
    "src/picture_capture/layout_physical_indent.py",
    "def _logical_slots_for_oversized_run(\n",
    "\n\ndef projection_line_runs(",
    '''def _logical_slots_for_oversized_run(
    y0: int,
    y1: int,
    reference: float,
) -> list[tuple[int, int]]:
    """Split one unresolved tall band without silently discarding long spans."""
    start = int(y0)
    stop = int(y1)
    height = max(0, stop - start)
    ref = max(6.0, float(reference))
    if height < ref * 1.55:
        return [(start, stop)] if stop > start else []

    # The downstream acceptance window is <= 1.90 * ref. Ensure the fallback
    # creates enough slots to satisfy that contract even for a very long band.
    by_reference = max(2, int(round(height / ref)))
    by_maximum_height = max(2, int(math.ceil(height / (ref * 1.90))))
    count = max(by_reference, by_maximum_height)

    # A normal 4600px dictionary page with ~35-60px text height stays well below
    # this. The cap prevents pathological/corrupt inputs from allocating an
    # unbounded number of slots while still allowing whole-page dense bands.
    count = min(256, count)

    # If the hard cap was ever reached, make sure the produced slot height still
    # honours the downstream maximum; otherwise retain the original band rather
    # than manufacture slots that would immediately be discarded again.
    if height / float(count) > ref * 1.90:
        return [(start, stop)]

    edges = np.linspace(float(start), float(stop), count + 1)
    slots: list[tuple[int, int]] = []
    for index in range(count):
        a = int(round(edges[index]))
        b = int(round(edges[index + 1]))
        if b > a:
            slots.append((a, b))
    return slots or ([(start, stop)] if stop > start else [])
''',
)

# 2. Remove installer plumbing now that the physical-indent helper is static.
replace_once(
    "src/picture_capture/bootstrap/gui.py",
    "    from ..layout_row_recovery_runtime import install_layout_row_recovery_runtime\n",
    "",
)
replace_once(
    "src/picture_capture/bootstrap/gui.py",
    '''    # Dense dictionary columns can form long continuous projection bands. Keep
    # those rows recoverable before any page-specific indent/drift measurement.
    install_layout_row_recovery_runtime()
    # Keep semantic column geometry fixed while allowing analysis pixels to
''',
    '''    # Long-band logical row recovery is now static in layout_physical_indent.
    # Keep semantic column geometry fixed while allowing analysis pixels to
''',
)

replace_once(
    "src/picture_capture/bootstrap/worker.py",
    "    from ..layout_row_recovery_runtime import install_layout_row_recovery_runtime\n",
    "",
)
replace_once(
    "src/picture_capture/bootstrap/worker.py",
    '''    install_processing_entry_classification(processing_module)
    install_layout_row_recovery_runtime()
    # Keep column-drift installation after row recovery, matching the historical
    # GUI and worker ordering. The physical-indent finalizer remains idempotent.
    install_layout_column_drift_runtime()
''',
    '''    install_processing_entry_classification(processing_module)
    # Long-band row recovery is static in layout_physical_indent. Column drift
    # remains an explicit process-local runtime until its own slice is proven.
    install_layout_column_drift_runtime()
''',
)

replace_once(
    "src/picture_capture/spawn_layout_runtime.py",
    '''"""Keep Page/Layout runtime installation identical in GUI and spawn workers.

``processing._understand_page_current`` calls ``_ensure_layout_runtime`` inside
ordinary-drawing workers.  The GUI composition root installs four physical
Layout runtimes in this order, but historically the worker-local helper installed
only the first two.  On pages whose second column drifts slightly, that difference
can turn many body rows into false indentation entries even though the GUI Layout
diagnostic is correct.

This compatibility adapter extends the worker helper rather than duplicating the
Page Understanding algorithm. The explicit shared ``bootstrap.core`` profile
installs it for GUI, worker, CLI and other composed application consumers; bare
package import intentionally performs no runtime installation.
"""
''',
    '''"""Keep the remaining Page/Layout runtime installation identical in workers.

``processing._understand_page_current`` calls ``_ensure_layout_runtime`` inside
ordinary-drawing workers. Long-band row recovery now lives statically in
``layout_physical_indent``. The worker-local helper still needs the same
column-drift runtime as GUI composition before Layout Core imports/calls the page
policy; otherwise drifting columns can produce false indentation entries.

This compatibility adapter extends the worker helper rather than duplicating the
Page Understanding algorithm. The explicit shared ``bootstrap.core`` profile
installs it for GUI, worker, CLI and other composed application consumers; bare
package import intentionally performs no runtime installation.
"""
''',
)
replace_once(
    "src/picture_capture/spawn_layout_runtime.py",
    '''        # GUI composition then installs these two. Spawn workers must do the
        # same before Layout Core imports/calls the page policy.
        from .layout_row_recovery_runtime import install_layout_row_recovery_runtime
        from .layout_column_drift_runtime import install_layout_column_drift_runtime

        install_layout_row_recovery_runtime()
        install_layout_column_drift_runtime()
''',
    '''        # Long-band row recovery is static. Spawn workers still need the
        # same column-drift runtime as GUI before Layout Core calls page policy.
        from .layout_column_drift_runtime import install_layout_column_drift_runtime

        install_layout_column_drift_runtime()
''',
)

replace_once(
    "src/picture_capture/unlined_physical_rows_resolver.py",
    "    from .layout_row_recovery_runtime import install_layout_row_recovery_runtime\n",
    "",
)
replace_once(
    "src/picture_capture/unlined_physical_rows_resolver.py",
    '''    install_robust_line_starts()
    install_physical_indent_inference()
    install_layout_row_recovery_runtime()
    install_layout_column_drift_runtime()
''',
    '''    install_robust_line_starts()
    install_physical_indent_inference()
    # Long-band row recovery is already static in layout_physical_indent.
    install_layout_column_drift_runtime()
''',
)

replace_once(
    "src/picture_capture/layout_rows_cache.py",
    '''    from .layout_physical_indent import _credible_first_ink_x, projection_line_runs
    from .layout_row_recovery_runtime import install_layout_row_recovery_runtime

    # Keep long dense projection bands from silently collapsing to four rows.
    install_layout_row_recovery_runtime()

''',
    '''    from .layout_physical_indent import _credible_first_ink_x, projection_line_runs

    # projection_line_runs statically preserves long dense projection bands.

''',
)

# 3. Ratchet runtime debt and remove the retired module.
replace_once(
    "scripts/architecture_guard.py",
    '    "layout_row_recovery_runtime.py",\n',
    "",
)
runtime = ROOT / "src/picture_capture/layout_row_recovery_runtime.py"
if not runtime.is_file():
    raise SystemExit("layout_row_recovery_runtime.py missing before migration")
runtime_text = runtime.read_text(encoding="utf-8")
for marker in (
    "def logical_slots_without_loss(",
    "def install_layout_row_recovery_runtime()",
    "physical._logical_slots_for_oversized_run = logical_slots_without_loss",
):
    if marker not in runtime_text:
        raise SystemExit(f"unexpected row-recovery runtime shape: missing {marker}")
runtime.unlink()

# 4. Convert runtime-characterization tests to direct static ownership tests.
long_test = ROOT / "tests/test_layout_long_band_row_recovery.py"
long_test.write_text('''from __future__ import annotations

from pathlib import Path

from picture_capture.layout_physical_indent import (
    _logical_slots_for_oversized_run as logical_slots_without_loss,
)


def test_ten_line_high_continuous_band_is_not_limited_to_four_slots():
    slots = logical_slots_without_loss(0, 400, 40.0)

    assert len(slots) == 10
    assert slots[0][0] == 0
    assert slots[-1][1] == 400
    assert all(1 <= end - start <= 76 for start, end in slots)


def test_long_page_band_stays_within_projection_acceptance_height():
    slots = logical_slots_without_loss(0, 4440, 37.0)

    assert len(slots) > 4
    assert slots[0][0] == 0
    assert slots[-1][1] == 4440
    assert all(end - start <= 37.0 * 1.90 for start, end in slots)


def test_physical_indent_statically_owns_long_band_fallback():
    root = Path(__file__).resolve().parents[1]

    assert logical_slots_without_loss.__module__ == "picture_capture.layout_physical_indent"
    assert not (root / "src/picture_capture/layout_row_recovery_runtime.py").exists()


def test_entry_paths_no_longer_install_row_recovery_runtime():
    root = Path(__file__).resolve().parents[1]
    paths = (
        "src/picture_capture/bootstrap/gui.py",
        "src/picture_capture/bootstrap/worker.py",
        "src/picture_capture/spawn_layout_runtime.py",
        "src/picture_capture/unlined_physical_rows_resolver.py",
        "src/picture_capture/layout_rows_cache.py",
    )
    for relative in paths:
        source = (root / relative).read_text(encoding="utf-8")
        assert "install_layout_row_recovery_runtime" not in source
''', encoding="utf-8")

replace_between(
    "tests/test_layout_column_drift_runtime.py",
    "def test_runtime_order_is_preserved_across_core_gui_and_worker_composition():\n",
    "__PHASE5Q_EOF__",
    '''def test_static_row_recovery_keeps_column_drift_runtime_explicit():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    core = (root / "src/picture_capture/bootstrap/core.py").read_text(encoding="utf-8")
    gui = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")
    worker = (root / "src/picture_capture/bootstrap/worker.py").read_text(encoding="utf-8")
    physical = (root / "src/picture_capture/layout_physical_indent.py").read_text(encoding="utf-8")

    # Shared process setup is complete before processing is imported.
    assert core.index("install_ordinary_large_head_role_guard()") < core.index(
        "from .. import processing as processing_module"
    )

    # Row recovery is static; the broader column-drift seam remains explicit.
    assert "install_layout_row_recovery_runtime" not in gui
    assert "install_layout_row_recovery_runtime" not in worker
    assert "install_layout_column_drift_runtime()" in gui
    assert "install_layout_column_drift_runtime()" in worker
    assert "count = min(256, count)" in physical
''',
)

# replace_between normally needs a real end marker; the function above is the
# last block in this test file, so handle the synthetic EOF marker explicitly.
column_test = ROOT / "tests/test_layout_column_drift_runtime.py"
column_text = column_test.read_text(encoding="utf-8")
if "__PHASE5Q_EOF__" in column_text:
    column_text = column_text.replace("__PHASE5Q_EOF__", "")
    column_test.write_text(column_text, encoding="utf-8")

replace_once(
    "tests/test_runtime_entry_path_guards.py",
    '    assert "install_layout_row_recovery_runtime()" in worker\n',
    '    assert "install_layout_row_recovery_runtime" not in worker\n',
)

replace_once(
    "tests/test_spawn_layout_runtime.py",
    '''    # This is exactly the worker-local entry point used before Layout Core runs.
    processing._ensure_layout_runtime()

    assert bool(getattr(physical, "_long_band_row_recovery_installed", False))
    assert bool(getattr(policy, "_column_drift_runtime_installed", False))
''',
    '''    # Row recovery is already static before the worker-local runtime entry.
    static_helper = physical._logical_slots_for_oversized_run
    slots = static_helper(0, 400, 40.0)

    # This is exactly the worker-local entry point used before Layout Core runs.
    processing._ensure_layout_runtime()

    assert physical._logical_slots_for_oversized_run is static_helper
    assert len(slots) == 10
    assert bool(getattr(policy, "_column_drift_runtime_installed", False))
''',
)

print("Phase 5Q migration applied")
