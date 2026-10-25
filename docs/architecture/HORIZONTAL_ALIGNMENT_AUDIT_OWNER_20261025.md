# Round 53 — horizontal alignment safety audit (2026-10-25)

Draft PR #663 / Issue #562. The robust multi-column geometry comparison and
verdict implementation has **one physical owner**:
`preprocess/horizontal_alignment_audit.py`.

## Migration scope

Moved complete numerical bodies for five routines:
`_horizontal_row_stats`, `_horizontal_region_angles`,
`_horizontal_tail_p90_abs`, `_horizontal_metric`,
`audit_horizontal_alignment`. The last includes row/column pair aggregation,
local top-middle-bottom regions, worst-column and bottom-tail analysis,
dual-edge safety gates and all original improvement criteria.

`preprocess/geometry.py` retains the exact original callable names, signatures,
live safety thresholds, and original frozen/pickle-visible
`HorizontalAlignmentAudit` class. The owner imports no `geometry.py` or Tk.
Every external dependency (column reconstruction, polygon edge metrics,
row/regional/tail statistics, result constructor and six safety constants) is
captured **per call** in immutable `HorizontalAuditOps`. The two weighted
statistics helpers are also injected at invocation so historical monkeypatch
seams remain working. No mutable module-global registry or installer.

Original column grouping and row extraction remain in `geometry.py` for the
next narrowly scoped step, avoiding a layout-model import cycle.
The five numerical bodies were moved mechanically without changes to
percentiles, MAD, weights, thresholds, worst-column/tail gates or verdicts.

Focused regression checks the physical owner/leaf import, runtime monkeypatch,
synthetic per-column improvement and tightened-threshold denial, missing rows,
numeric fitting, exact original callable signatures and report pickle identity.
Existing multi-column and perspective regression runs unchanged.

No PDIC/PPP/SECTION, Profile, OCR model/cache, Tk callback, original-coordinate,
crop/export or project-storage changes. Exact-head full CI and 3-OS OCR smoke
are still required; scanned real dictionary page parity is a separate human
gate. Keep Draft PR open and unmerged.
