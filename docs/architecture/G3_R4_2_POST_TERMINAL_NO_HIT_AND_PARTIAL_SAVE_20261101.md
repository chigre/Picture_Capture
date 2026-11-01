# G3 R4.2 — post-terminal no-hit epoch validation and multi-page partial-save uncertainty

**Date:** 2026-11-01  
**Repository:** `chigre/Picture_Capture`  
**Branch:** `refactor/562-retire-root-image-utils-20261024`  
**Source/test HEAD:** `fd4f46b717de23c96014661ae28cedef51434788`  
**Main:** `ec20989ea8c026cca5337293e67850b6b6df30f2` (unchanged)  
**PR:** [#663 — Draft / Open / Unmerged](https://github.com/chigre/Picture_Capture/pull/663)

## Scope

This checkpoint closes two remaining B4/R4.2 consistency gaps found after the earlier source-witness and save-owner work:

1. A no-hit page remains part of the scan's false-negative boundary after the scan reaches terminal completion. A later PDIC/OCR/SECTION change must invalidate stale rows before another batch is published, including while a crop payload is in flight.
2. A multi-page focused save is not a cross-file transaction. If one page has been published and a later page writer fails or has an uncertain outcome, the UI must not claim a globally committed batch, silently close, auto-retry, or roll back files that may already have been published.

All new cases use disposable synthetic fixtures and injected workers/writers. No real dictionary, OCR payload, private PDIC/PPP/SECTION/Profile, or operator data was read or written.

## 1. Post-terminal no-hit epoch validation

### Failure-first and intermediate regression

- Test commit [`35bbeed90f943c50854e0b8a12ea4b8db5fa3f25`](https://github.com/chigre/Picture_Capture/commit/35bbeed90f943c50854e0b8a12ea4b8db5fa3f25) added a regression where a previously no-hit page changes after scan completion and while a crop payload is pending.
- [CI #41295513470](https://github.com/chigre/Picture_Capture/actions/runs/41295513470) failed on all six regression jobs; the Ubuntu Python 3.13 log records the intended crop-publication failure (1 failed, 5,286 passed, 3 skipped). The no-hit page's SECTION source could change while the old crop payload was still eligible to complete.
- Source commit [`fa430d854e11255a4d0e7dfce1406036f47d00ea`](https://github.com/chigre/Picture_Capture/commit/fa430d854e11255a4d0e7dfce1406036f47d00ea) added epoch invalidation and checks around cache/payload application. A subsequent performance-oriented relocation in [`af77de193984d27e3725c0ddd1b6dd8e19a35a0b`](https://github.com/chigre/Picture_Capture/commit/af77de193984d27e3725c0ddd1b6dd8e19a35a0b) moved checks away from repeated repaint/prefetch work, but [CI #41295775912](https://github.com/chigre/Picture_Capture/actions/runs/41295775912) exposed three post-terminal PDIC/OCR/SECTION drift failures. This intermediate failure was not treated as success.
- Minimal correction [`194df65fd8f9e6e3a77bb8071380d8897609341d`](https://github.com/chigre/Picture_Capture/commit/194df65fd8f9e6e3a77bb8071380d8897609341d) restored validation at the actual batch-publication boundary.

### Current behavior

- Every scanned page retains its PDIC/OCR/SECTION source witness in the active epoch, including pages returning zero targets.
- Chunk terminals validate the scanned prefix before publishing additional rows or declaring the scan complete.
- After terminal completion, the retained epoch is revalidated at the actual batch-publication boundary. This includes no-hit pages and prevents stale results being presented as complete after source drift.
- In-flight crop/prefetch payloads are rejected when their epoch/source ownership is stale; the epoch is invalidated, render/prefetch work is invalidated, and the user is asked to re-filter. Human edits are not discarded.
- Validation is deliberately not performed on every repaint or every background prefetch. This avoids multiplying full-epoch hashing across incidental UI refreshes while retaining a check at the point where rows are actually published.

## 2. Multi-page focused-save partial publication

### Failure-first and correction history

- Test commit [`684693053aa2b958226ab44b674d2c1acdf5e861`](https://github.com/chigre/Picture_Capture/commit/684693053aa2b958226ab44b674d2c1acdf5e861) added a synthetic two-page partial-publication regression. [CI #41296691853](https://github.com/chigre/Picture_Capture/actions/runs/41296691853) failed as expected: the first page's returned write and the second page's failure left the original batch state inconsistent with the test's intended contract.
- An initial source change in [`63a93fa0a1d931f4b8bc5a73ea6a6e82114e12b4`](https://github.com/chigre/Picture_Capture/commit/63a93fa0a1d931f4b8bc5a73ea6a6e82114e12b4) attempted page-level reconciliation. Further review rejected treating the multi-page operation as a transaction and strengthened the test to require conservative batch-level uncertainty.
- Test update [`e1d376df89e622ffe081ea27c2960dd600dcd9cc`](https://github.com/chigre/Picture_Capture/commit/e1d376df89e622ffe081ea27c2960dd600dcd9cc) was intentionally RED at [CI #41297732941](https://github.com/chigre/Picture_Capture/actions/runs/41297732941). The run recorded 28 failures across the six regression jobs, including an unbound `recovered` value in successful-save reconciliation, a legacy synthetic owner without `filtered_targets`, and stale save-failure wording assertions. These failures were inspected and fixed; they were not waived.
- Final minimal source correction is [`fd4f46b717de23c96014661ae28cedef51434788`](https://github.com/chigre/Picture_Capture/commit/fd4f46b717de23c96014661ae28cedef51434788): successful completion now computes the recovery result before using it; reconciliation tolerates legacy helper doubles without a `filtered_targets` attribute; and the failed/uncertain path retains the entire batch snapshot, marks the batch pages uncertain, disables close-after-save, cancels debounce auto-retry, and emits a generic redacted failure message.

### Current safety contract

- All page image/SECTION source witnesses are preflighted before the first PDIC write.
- A clean worker completion reconciles verified saved rows. A writer exception after dispatch is not proof that the page was untouched: publication may have occurred before the exception.
- If any page writer in a multi-page batch raises after dispatch, the complete human-edit snapshot is retained and every page in that batch is marked `UNCERTAIN` pending explicit inspection/retry. This is intentionally conservative, including pages that may have returned earlier or were not attempted later.
- Automatic timer/debounce retry is blocked while uncertain pages remain. The user must inspect the PDIC state and use the explicit retry path.
- No rollback is attempted against a page file that may already contain a valid published write. Newer in-flight edits and explicit user reversions retain ownership in the pending queue.
- The operation remains a sequence of per-page writes, not an OS-level atomic multi-file transaction. No persisted schema, PDIC/SECTION serialization format, original image coordinates, or save writer format was changed.

## 3. Exact current-HEAD verification

At source/test HEAD `fd4f46b717de23c96014661ae28cedef51434788`:

- [CI #41298152181](https://github.com/chigre/Picture_Capture/actions/runs/41298152181): **SUCCESS**, all six Windows/macOS/Ubuntu × Python 3.10/3.13 regression jobs; Risk-tier and Risk-tier CI gate **SUCCESS**.
- [OCR Platform Smoke #41298152176](https://github.com/chigre/Picture_Capture/actions/runs/41298152176): **SUCCESS, 3/3**.
- [PR CodeQL #41298149721](https://github.com/chigre/Picture_Capture/actions/runs/41298149721): Analyze Python and Actions **2/2 SUCCESS**.
- Documentation architecture check: **SKIPPED**, not counted as PASS.
- The full CI also reruns the R5.1/R5.2 parity suites; this remains synthetic E2 evidence only.

## 4. Boundaries and remaining work

- No real benchmark or profiling was run; no acceleration, accuracy, or OCR-quality claim is made.
- SHA-256 readback is not an OS-level multi-file compare-and-swap, file lock, or atomic filesystem snapshot.
- No real dictionary scan or real PDIC/PPP/SECTION/Profile/OCR save/reopen was performed.
- **NOT PERFORMED:** Windows R3 E3; #483 W1–W11; #503 manual Undo/Redo; real operator acceptance.
- **DEFERRED:** R6 human-label learning/shadow output and R8 real scan.

## 5. Next recovery point

B4/R4.2 is synthetic E2 complete. B6 remains blocked by the absence of authorized, reliable human-verified source-consistent labels. B7a/R7.1–R7.2 remains blocked until representative authorized profiling exists. The next independent non-human work item is B7b/R7.3: audit and define a read-only source → canonical → transformed coordinate contract with synthetic round-trip tests for SECTION, PDIC, PPP, ROI polygons and crops. Do not migrate persisted schema, change original coordinates, or alter save/write flows.
