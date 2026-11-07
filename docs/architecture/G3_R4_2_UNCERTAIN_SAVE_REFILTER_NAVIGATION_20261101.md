# G3 R4.2 — Uncertain-save re-filter / batch-navigation guard (2026-11-01)

## Owner and failure condition
`ui/focused_filter_workflow.py` owns the transient filtered-row scan epoch, pending human corrections, save launch failures and per-page uncertain outcomes. A previously dispatched PDIC writer may have changed disk bytes even when its launch/terminal result cannot be proven. A temporarily empty debounce queue does **not** settle that ownership.

Two bypasses survived the earlier close/timer protections:
1. `run_focused_filter` checked only running writer/pending edits. With `_filter_save_uncertain_pages` nonempty **or** `_filter_save_launch_failed` true and an empty pending queue, a fresh scan could overwrite the current scan epoch and its reconciliation context.
2. `change_filter_batch` called `_flush_focused_changes_now()` before checking unresolved outcomes. The helper intentionally sets the explicit-retry flag, so ordinary Next-batch navigation could re-dispatch an uncertain page writer without the operator first reviewing PDIC.

## Real RED-first GitHub evidence (failed, not release gates)
- Test-only [`d8b65be7`](https://github.com/chigre/Picture_Capture/commit/d8b65be7ed8aeed0bfab022c69cf5860a1863fd0): [CI #41311186833](https://github.com/chigre/Picture_Capture/actions/runs/41311186833), Ubuntu Python 3.13 **2 targeted failures / 5,302 passed / 3 skipped**; existing code started a replacement scan despite unresolved page or scheduler-launch uncertainty.
- Test-only [`ae1f21ed`](https://github.com/chigre/Picture_Capture/commit/ae1f21edbfff17e5a554b6e97dd7787e3be7c0a3): [CI #41311282890](https://github.com/chigre/Picture_Capture/actions/runs/41311282890), Ubuntu Python 3.13 **3 targeted failures / 5,301 passed / 3 skipped**; new navigation assertion showed an unintended implicit retry alongside the two previous re-filter failures.
- Tests reside in `tests/test_g3_r4_scan_source_consistency_20261101.py` and `tests/test_g3_r4_focused_launch_uncertainty_20261101.py`. Positive controls require rescan after explicit settling and preservation of the existing real explicit retry path.

## Bounded production correction
[`eff2b7c8`](https://github.com/chigre/Picture_Capture/commit/eff2b7c8e269bb4f6ecec414cffdff059e9dabdb) changes only `src/picture_capture/ui/focused_filter_workflow.py`:
- Refuse re-filter before persisting scan settings or resetting scan epoch if any save-launch or per-page outcome remains uncertain, regardless of whether the edit queue happens to be empty.
- Refuse target-batch navigation **before** invoking the helper that grants explicit retry. Preserve visible current batch and human edits. Show a generic status asking the operator to inspect PDIC and retry through the explicit save action.
- With no uncertain marker, original re-filter, ordinary batch navigation and explicit save retry are unchanged.

## Checks, constraints and remaining work
Exact source-HEAD [CI #41311452549](https://github.com/chigre/Picture_Capture/actions/runs/41311452549) (Windows/macOS/Ubuntu × Python 3.10/3.13, Risk-tier), [OCR #41311452557](https://github.com/chigre/Picture_Capture/actions/runs/41311452557), and CodeQL Python/Actions must be read at terminal state; this note was drafted before final result, so **do not infer success**. A separate docs-head gate is required after publishing this audit.

No persisted PDIC/PPP/SECTION/Profile/OCR format or original coordinates, underlying writer, experiment default, or real user data were altered. Per-page uncertainty remains transient, **not** a durable multi-file transaction or OS-level compare-and-swap.

**NOT PERFORMED:** Windows R3 E3, #483 W1–W11, #503 human Undo/Redo, authentic scanned dictionary pages, real PDIC/PPP/SECTION/Profile/OCR save/reopen and operator sign-off. **DEFERRED:** R6 real-label training, R8 real scan; no performance/F1 claim. PR #663 stays Draft/Open/Unmerged; main untouched.

**Next:** verify exact current-head gates and PR review threads, then continue synthetic async epoch/SECTION/crop-preload/save reconciliation auditing.
