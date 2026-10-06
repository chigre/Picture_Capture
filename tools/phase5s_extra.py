from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "tests/test_large_head_row_front_runtime.py"
source = path.read_text(encoding="utf-8")

replacements = (
    (
        "def test_column_drift_runtime_never_replaces_large_head_detector():",
        "def test_static_column_drift_helper_never_replaces_large_head_detector():",
    ),
    (
        'root / "src/picture_capture/layout_column_drift_runtime.py"',
        'root / "src/picture_capture/layout_column_drift.py"',
    ),
    (
        "    # Column drift owns first-X remeasurement only. Reintroducing an assignment\n"
        "    # here would silently bypass row-front/strong-oversized guards because Layout\n"
        "    # Core imports the detector later in the real GUI/spawn path.\n",
        "    # Static column drift owns first-X remeasurement only. Reintroducing an\n"
        "    # assignment here would silently bypass row-front/strong-oversized guards.\n",
    ),
)
for old, new in replacements:
    if source.count(old) != 1:
        raise RuntimeError(f"unexpected large-head guard test anchor: {old!r}")
    source = source.replace(old, new, 1)

path.write_text(source, encoding="utf-8")
print("Phase 5S stale large-head source-contract test updated")
