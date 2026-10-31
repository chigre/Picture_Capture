# G3 R4.2 — initial and streamed remainder scan one-shot terminal ownership

Date (Singapore): 2026-11-01. Sole Draft PR #663. This is synthetic automated E2, not human or real dictionary acceptance.

## Baseline, failure, and risk

A current live GitHub audit confirmed `main@ec20989ea8c026cca5337293e67850b6b6df30f2`, sole Draft/Open/Unmerged PR #663, Issues #503/#562/#483 Open and 0 unresolved review threads. Baseline `97cabc347c28085b0e970947e347a7fc376f8782` had fully completed [CI #41219251436](https://github.com/chigre/Picture_Capture/actions/runs/41219251436) six Windows/macOS/Ubuntu×Python3.10/3.13+Risk, [OCR #41219251550](https://github.com/chigre/Picture_Capture/actions/runs/41219251550) three platforms, [CodeQL #41219246937](https://github.com/chigre/Picture_Capture/actions/runs/41219246937) Python+Actions, all success.

Initial scan `first_done/failed` and remainder scan `remaining_done/failed` checked epoch and active mode, but had no per-dispatch terminal ownership. A duplicate first success can schedule an additional remainder; a late failure can erase already rendered targets. A repeated remainder success appends the same rows twice; a late failure marks an actually completed scan incomplete. A repeated failed scan can write redundant status/indicator UI even when the text does not change.

Test-only `cd77a0aac4250adca5a2e2008e04e294ea1ffddc` added eight parameterized two-chunk synthetic scan tests (success→success, success→failed, failed→success, failed→failed for initial and remainder). [CI #41222862870](https://github.com/chigre/Picture_Capture/actions/runs/41222862870) Ubuntu Python3.13 **observed 7 targeted FAILED / 5,212 passed / 3 skipped**; the repeated remainder failure was not detected by string-value comparison alone. Second test-only `41c92b63e80b786ff5b32147e355c5fb09e2e7e8` instrumented test `Var.writes` and forbids duplicate same-value status/indicator writes, retaining all original assertions. It does not change product behavior. [Enhanced test CI #41223121982](https://github.com/chigre/Picture_Capture/actions/runs/41223121982) is separate red-first evidence and its actual terminal status must be checked, not assumed.

## Minimal product correction

`405df1384e78a9658d3f1759e2a38ea0fd7abd8b` changes only `src/picture_capture/ui/focused_filter_workflow.py`:
1. `first_terminal_claimed` belongs to the first scan dispatch. Both callbacks reject already claimed work; the active scan epoch / filter-mode check precedes the first claim.
2. Each invocation of `start_remaining_scan` constructs an independent `remaining_terminal_claimed`. Its done/failed handlers likewise claim first terminal ownership before mutating/clearing `filtered_targets`, changing status, setting incomplete flag, or starting the next worker.
3. Stale old scan/mode callbacks remain inert. No changes to accepted scan-page matching, no source XY remapping, no PDIC/PPP/SECTION/Profile persistence, no new retries, no debugging of private paths, and no write to real OCR or dictionary data.

This guard proves duplicate/contradictory events from an *accepted* dispatch cannot mutate the same epoch twice. It does not prove OS-level multi-file CAS or substitute for operator-driven UI acceptance. No claim of faster scanning, better OCR accuracy or production correctness beyond the synthetic matrix.

## Exact-head gates and manual limits

At this audit commit, the final code+docs SHA must still independently obtain completed six OS/Python CI jobs and Risk tier/gate, OCR three-platform Smoke, CodeQL Python/Actions 2/2. Record results in a **post-gate PR #663 comment** without an unnecessary unverified docs-only commit. Keep red intermediate failures in the record.

**NOT PERFORMED:** Windows R3 E3, #483 W1–W11, #503 complex/manual Undo/Redo, actual dictionary OCR/crop/PDIC/PPP/SECTION/Profile reopen, real XY and benchmark. Automated E2 does not imply human E3.
**DEFERRED:** R6 verified user labels and R8 real scans. No real private files uploaded. Keep PR #663 Draft/Open/Unmerged, main unchanged, and blocker Issues Open.

## Next recovery

Re-read main, PR HEAD, comments and exact-head gates; continue other unblocked R3–R7 work including genuine SECTION source transitions, concurrent save/prefetch ownership, and optional scan-source provenance. New work must be test-first with a distinct reproducible failure and no forced parallel branch updates.
