# PC-CQ v1.3.0 G1 — filtered review save/page-mode gate (2026-10-29)

## Source-derived loss path
Filtered ReviewWindow editor changes are saved with an asynchronous, page/XY-
guarded worker (`focused_filter_workflow._flush_focused_changes`).
`review_page_sync.save_review_before_page_change` skipped filtered view
entirely, and `review_workspace_workflow._change_review_mode` immediately
discarded filtered rows after merely **starting** the worker. If the worker
later failed, pending edits were requeued without maintaining their source
visible editing view. This is a race, not a proven OS-level atomicity failure.

## Fail-first and bounded fix
- Fail-first tests-only HEAD `fcf32587328391b37e205606e1f4199617bcae09`
  and `tests/test_g1_filter_unsaved_navigation_gate_20261029.py` verify
  filter-specific main page save refusal, mode switch while background worker
  runs or pending edits exist, and the unaffected clean mode switch.
- `review_page_sync` now asks the active filter review to flush and waits by
  **refusing navigation** (existing None sentinel) while a pending/running
  write exists. Only once finished may main navigation proceed. A filter
  save does not own any single-page rendered Entry; ordinary main-canvas
  save responsibility stays unchanged.
- `review_workspace_workflow` does not discard current filter rows when
  `_filter_save_running` or `_filter_pending_changes` remains after flush.
  It restores the `filter` radio state and gives an operator message.
- No extra autosave worker, bypassed source check, guessed XY, OCR rerun,
  persisted format, new root facade or changed background worker semantics.

## Validation and exclusions
Record final exact-head Windows/macOS/Ubuntu Python 3.10/3.13 CI,
OCR Platform Smoke 3/3, PR CodeQL Python/Actions. These are E2 synthetic,
not actual human Windows dictionary-page acceptance. R3 20-step Undo/Redo,
FocusOut/IME, PDIC/PPP/SECTION save-reopen, crop parity, and #483 W1–W11
remain NOT PERFORMED. Do not merge #663 or mark Ready; #503/#562 stay open.
