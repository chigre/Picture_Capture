# PC-CQ v1.3.0 G1 — failed/conflicted filtered PDIC worker recovery (2026-10-29)

## Verified source-level race
`focused_filter_workflow._flush_focused_changes` extracts a pending
page/XY snapshot, launches the existing one-at-a-time background worker,
and permits new edits while that worker runs.

- On worker exception, old code restored each snapshot change **over**
  `_filter_pending_changes` unconditionally, potentially erasing a later
  correction at the exact same original-image page/X/Y.
- On page/XY conflict, the writer returns `([], conflicts)` for that page.
  Old success callback had already cleared the snapshot; it could complete
  a deferred close despite the unresolved human correction.
- If a user reverted the active target to its original word while a worker
  ran, unconditional snapshot replay could resurrect the unwanted old edit.

## Scope / fail-first
Tests-only `53a1d30900db3de706b77c6d12778ae98d865cef`;
`tests/test_g1_filter_failed_worker_conflict_latest_edits_20261029.py`.
Five callback tests: newer same-XY edit survives worker failure; pending
work remains and deferred-close is cancelled on exception; a conflicted
page cannot lose its snapshot or close; successful commit still closes;
a reverted target cannot be resurrected by an old failed snapshot.

Fix is solely within `ui/focused_filter_workflow.py`, retaining the
existing source-coordinate writer, callback ABI, R3 PDIC transaction and
single worker. A local restore helper requeues **only unsaved original
snapshot entries**, gives a pending newer edit precedence, and respects
a visible target that was explicitly reverted to its source word.
Conflicts cancel deferred-close and retain unresolved changes without
automatic infinite retry; a later explicit operator save may retry.
Exceptions also cancel deferred-close and preserve pending work.

No invented CAS, cross-file atomicity, power-loss durability, automatic
resolution of conflicting X/Y, or background writer redesign.
Automated E2 is not Windows GUI E3. The R3 human FocusOut/IME,
20-step Undo/Redo, PDIC/PPP/SECTION reopen, exact-pixel/crop validation
and #483 W1–W11 remain **NOT PERFORMED**. PR #663 stays Draft/Open/Unmerged;
#503/#562 remain open.
