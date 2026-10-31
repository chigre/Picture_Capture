# G3/R3 focused save: synchronous completion before scheduler acknowledgement

Date: 2026-10-31. Current work remains in the sole [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663), unmerged. No real images or source records were used.

## Specific boundary

`focused_filter_workflow._flush_focused_changes` submits a background save through `parent._start_ui_worker(name, worker, done, failed)`. Earlier protection (verified at `19ffa6a955f74016aba2fef2502567974ec42a1c`) restored unconfirmed corrections after a **synchronously raised launch exception**, and used a monotonic dispatch serial to isolate callbacks from an **older** launch after a later retry. It had no ordering fence for the more adversarial condition where the scheduler invokes `done` or `failed` **inside its call** and then throws before returning.

Without a handoff fence, a synchronous `done(saved,[])` could update `filtered_targets[*].original_word`, reconcile model/UI and invoke `_finish_close_review` while the launch remained unacknowledged. A `failed` inside launch could display a failure dialog and then the launch exception would display a second one. Even a successfully returned scheduler could send the terminal callback twice. These are callback contract risks; this synthetic test does not assert that the current production scheduler normally sends callbacks reentrantly.

## Test first, minimum correction

- Test-only `140d981d48e227ca2a5ccd3a6c7d9bc31bf951ac` extends `tests/test_g3_r4_focused_dispatch_fail_closed_20261031.py` with 7 synthetic combinations: early `done/failed` × 2 prior close-intent values then launch failure; successful synchronous `done/failed` followed by duplicate contradictory terminal callback; successful acknowledged synchronous empty result retaining an unsaved correction. No actual disk publication is claimed from fake callback payloads.
- Production `3ed584a5d3c8dea7f938008f005ce4dc2e94248a` adds a per-dispatch local `pending/accepted/rejected` acknowledgement barrier. Before scheduler returns, retain only its first terminal callback in memory but do not act on it. If the scheduler raises, discard it, preserve human edits, disarm close and show a single generic failure. If the scheduler returns, deliver at most the first terminal callback to existing `done/failed` exactly once. Existing monotonic dispatch serial continues to reject a previous launch's delayed callbacks after a new one is accepted.
- **Observed genuine red-first:** test-only [CI #41190094623](https://github.com/chigre/Picture_Capture/actions/runs/41190094623) Ubuntu Python3.13 **6 failed / 5,079 passed / 3 skipped**; macOS Python3.13 **6 failed / 5,080 passed / 2 skipped**. The failures were all six targeted early/duplicate callback assertions, and the positive inline empty-result control passed. This intentionally red SHA is not an acceptable gate. The fixed-source [CI #41190137992](https://github.com/chigre/Picture_Capture/actions/runs/41190137992) was running at this checkpoint. Final docs HEAD requires fresh exact-head CI/OCR/CodeQL validation.

Native Tk synthetic test commit `9408c31d620b97f561274b31be85db0397ae761e` extends `scripts/gui_g3_focused_controls_smoke.py`: actual ReviewWindow StringVar/source-attested correction with **two** inline-completion-before-throw variants (early done and early failed), original-word/PDIC unchanged, precisely one generic Tk error, no closing, then a real explicit committed close. This runs on disposable synthetic project pages; not human E3.

## Safety boundaries and evidence

The fix touches neither PDIC/PPP/SECTION/manual-selection/Profile/OCR file bytes/formats nor source XY, worker's PDIC writer, real Tk ownership or default-OFF experimental policy. No filesystem rollback is inferred if a scheduler raises after starting a worker. The callback fence is a **per-process UI acknowledgement guard**, not a disk commit certificate, cross-file CAS or multi-page atomicity.

Final automated E2 requires Windows/macOS/Ubuntu × Python3.10/3.13 6/6 plus Risk-tier gate, OCR Smoke3/3, CodeQL Python/Actions2/2, no unresolved PR reviews and the identical final HEAD. Conditional documentation architecture check may SKIP without counting as passed. Windows human E3, #483 W1–W11, full #503 candidate compound Undo/Redo, G3 real dictionary scanning/performance, R6 real human labels and R8 real scans remain NOT PERFORMED / DEFERRED. Keep PR #663 Draft/Open/Unmerged.
