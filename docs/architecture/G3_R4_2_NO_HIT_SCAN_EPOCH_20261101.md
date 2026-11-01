# G3 R4.2 — no-hit page source retention across asynchronous scan epochs

**Date:** 2026-11-01  
**Repository:** `chigre/Picture_Capture`  
**Branch:** `refactor/562-retire-root-image-utils-20261024`  
**Source/test HEAD:** `3b06e89034cc8c5b93db3613fd0d10fe811bdc70`  
**PR:** [#663 — Draft / Open / Unmerged](https://github.com/chigre/Picture_Capture/pull/663)

## Problem found after the first source-binding fix

The preceding R4.2 source witness bound every returned target to its page's PDIC/OCR/SECTION bytes and rechecked target pages during crop snapshot/prefetch/direct rendering. However, a page with zero matching targets returned an empty list and its witness was not retained after `scan_page` returned. That left a scan-completeness gap: an earlier no-hit page could change while later streamed chunks were still being scanned, without invalidating the eventual “scan complete” claim.

This is distinct from crop correctness. A no-hit page has no crop row, but it still contributes to the false-negative boundary of the result set.

## Failure-first evidence

Test-only commit [`1a3e19e`](https://github.com/chigre/Picture_Capture/commit/1a3e19e2595fb6355b87e185305228994c54e00a) added `tests/test_g3_r4_no_hit_scan_epoch_source_20261101.py`.

The test scans four synthetic pages in three chunks:
1. page 001 produces zero target rows;
2. pages 002 and 003 produce visible rows and trigger subsequent chunks;
3. after page 001 has already returned, its PDIC, OCR JSON or SECTION bytes are mutated before the final chunk completes.

The exact test-first run [CI #41289415491](https://github.com/chigre/Picture_Capture/actions/runs/41289415491) completed FAILURE across all six Windows/macOS/Ubuntu × Python 3.10/3.13 jobs. Each of the three parameterized source mutations was accepted and the scan incorrectly reached completion. Ubuntu Python 3.13 and 3.10 each recorded 3 failed / 5,280 passed / 3 skipped. This is the intended RED evidence.

## Minimal source correction

Production commit `3b06e89034cc8c5b93db3613fd0d10fe811bdc70` changes only `ui/focused_filter_workflow.py`:

- A scan-epoch-local map retains `page_index → source witness` for every scanned page, whether it yields targets or not.
- Re-scanning the same page index with a different source witness fails instead of replacing the prior witness.
- The first batch completion and every remaining-chunk completion revalidate the entire scanned prefix before publishing that chunk or marking the scan complete.
- A source mismatch routes through the existing generic failure path: no current-chunk rows are published, the scan remains incomplete/failed, and already-ready editable batches remain available.

The implementation reuses the existing SHA-256 PDIC/OCR/SECTION witness; it adds no persistent field, does not change OCR or PDIC bytes, and does not modify crop geometry or the save writer.

## Exact source-head E2 evidence

At source/test HEAD `3b06e89034cc8c5b93db3613fd0d10fe811bdc70`:

- [CI #41289630397](https://github.com/chigre/Picture_Capture/actions/runs/41289630397): **SUCCESS, 6/6** Windows/macOS/Ubuntu × Python 3.10/3.13.
- Risk-tier and Risk-tier CI gate job `124798944251`: **SUCCESS**.
- [OCR Platform Smoke #41289630408](https://github.com/chigre/Picture_Capture/actions/runs/41289630408): **SUCCESS, 3/3**.
- [PR #663 CodeQL #41289628415](https://github.com/chigre/Picture_Capture/actions/runs/41289628415): Analyze Python and Actions **2/2 SUCCESS**.
- Python 3.13: Ubuntu **5,283 passed / 3 skipped**; macOS **5,284 / 2**; Windows **5,284 / 2**.
- Python 3.10: Ubuntu **5,283 passed / 3 skipped**; macOS **5,284 / 2**; Windows **5,284 / 2**.
- Documentation architecture check: **SKIPPED**, not counted as PASS.

These are synthetic automated E2 results, not operator E3 or real dictionary validation.

## Boundaries and remaining limitations

- The epoch witness map is in-memory and scoped to the active scan closure. It is rechecked at each chunk terminal, including the final terminal.
- After scan completion, later changes to a no-hit page are not continuously rechecked on every subsequent navigation. Target pages remain checked by the existing batch snapshot path. This is the next source-consistency extension to consider, with performance measured before adopting full-page rehashing on every UI action.
- SHA-256 readback is not an OS-level multi-file compare-and-swap, file lock or atomic filesystem snapshot.
- No save-writer or persisted-schema changes were made; no cross-page transaction is claimed.
- No real-data accuracy, latency or benchmark claim is made.

## Repository and operator state

- `main` remains `ec20989ea8c026cca5337293e67850b6b6df30f2`.
- #663 remains the sole development PR and stays Draft/Open/Unmerged.
- #503, #562 and #483 remain Open.
- No human E3 acceptance is inferred from these automated tests.
- **NOT PERFORMED:** Windows R3 E3; #483 W1–W11; #503 manual Undo/Redo; real dictionary scanning; real PDIC/PPP/SECTION/Profile/OCR save/reopen; operator acceptance.
- **DEFERRED:** R6 real-label learning and R8 real scan.

## Next recovery point

1. Commit this audit with synchronized `CORE_QUALITY_STATE.json` and `CORE_QUALITY_RESUME.md`.
2. Re-run exact-head six-platform CI, Risk-tier + gate, OCR 3OS and CodeQL on the documentation checkpoint HEAD. Do not count a skipped architecture check as pass.
3. Continue fail-first coverage for focused-save partial publication/reconciliation and post-terminal no-hit source drift.
