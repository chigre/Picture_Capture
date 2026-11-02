# G3 R4.2 — Streaming session identity and epoch serial binding (2026-11-03)

## Scope and invariant

This audit follows the synthetic project/ReviewWindow lifecycle guard package. The active focused-filter scan epoch must remain attached to the exact `ProjectState` object and to the serial that created its source-witness map.

Two checks are intentionally distinct:

1. **Session identity during streaming publication.** Commit `b2b4aa9b4a40a012fcbe0f7d560d6c80ecb3b878` moves the cheap ProjectState identity, root and page-list checks ahead of the incomplete-scan early return. A streaming crop/render callback therefore cannot publish against a reopened/replaced ProjectState merely because the scan has not reached its terminal state. Expensive page-source hashing remains at scan chunk terminals and actual batch-publication boundaries; this does not add full-epoch hashing to every repaint.
2. **Witness-map/serial binding.** A non-`None` epoch witness map is an active scan contract. It is valid only when `_filter_scan_epoch_source_serial == _filter_scan_serial`. Missing or mismatched serials are inconsistent ownership, not a reason to skip validation. The legacy no-witness helper path remains compatible.

No persistent schema, PDIC/PPP/SECTION format, image coordinates, OCR behavior, crop geometry, save writer, or experiment default changed.

## RED-first evidence

Test-only commit [`fc30ef6a3ae5522985d538758ffdf9a45b8e0cb0`](https://github.com/chigre/Picture_Capture/commit/fc30ef6a3ae5522985d538758ffdf9a45b8e0cb0) added:

- populated witness map with missing epoch serial;
- populated witness map with stale epoch serial;
- positive control: legacy call with no witness map remains accepted.

[RED CI #41504813347](https://github.com/chigre/Picture_Capture/actions/runs/41504813347) completed with the two intended failures in **all six** Windows/macOS/Ubuntu × Python 3.10/3.13 regression jobs. Each failure showed the helper returning `True` for a populated witness map with no matching serial.

| Matrix job | RED result |
|---|---:|
| Ubuntu Python 3.13 | 2 failed / 5,438 passed / 3 skipped |
| macOS Python 3.13 | 2 failed / 5,439 passed / 2 skipped |
| Windows Python 3.13 | 2 failed / 5,439 passed / 2 skipped |
| Ubuntu Python 3.10 | 2 failed / 5,438 passed / 3 skipped |
| macOS Python 3.10 | 2 failed / 5,439 passed / 2 skipped |
| Windows Python 3.10 | 2 failed / 5,438 passed / 3 skipped |

These were expected RED-first failures; they were not treated as a passing gate.

## Minimal source correction

Commit [`2fc347e3f806c5e2e961127fb2c5d83d191bf1df`](https://github.com/chigre/Picture_Capture/commit/2fc347e3f806c5e2e961127fb2c5d83d191bf1df) changes only `src/picture_capture/ui/focused_filter_workflow.py` (4 additions, 1 deletion): a populated witness map whose owner serial is missing or stale now returns `False`, allowing the existing caller to reject the epoch. The no-witness legacy path is unchanged.

## Exact source/test HEAD verification

Source/test HEAD: `2fc347e3f806c5e2e961127fb2c5d83d191bf1df`.

- [CI #41505337297](https://github.com/chigre/Picture_Capture/actions/runs/41505337297): **COMPLETED / SUCCESS**; six Windows/macOS/Ubuntu × Python 3.10/3.13 jobs and Risk-tier CI gate all succeeded.
- [OCR Platform Smoke #41505337406](https://github.com/chigre/Picture_Capture/actions/runs/41505337406): **3/3 SUCCESS**.
- [CodeQL / PR #663 #41505327430](https://github.com/chigre/Picture_Capture/actions/runs/41505327430): Analyze Python and Actions **2/2 SUCCESS**.
- Documentation architecture check: **SKIPPED**, not counted as PASS.

| Matrix job | GREEN result |
|---|---:|
| Ubuntu Python 3.13 | 5,440 passed / 3 skipped |
| macOS Python 3.13 | 5,441 passed / 2 skipped |
| Windows Python 3.13 | 5,441 passed / 2 skipped |
| Ubuntu Python 3.10 | 5,440 passed / 3 skipped |
| macOS Python 3.10 | 5,441 passed / 2 skipped |
| Windows Python 3.10 | 5,441 passed / 2 skipped |

Windows Python 3.13 logs additionally report native thumbnail controls, scrolling/sorting thumbnail and cell-border checks, native Tk focused refusal/retry/in-flight-reversion, and close/source-drift refusal smoke as OK. This is automated synthetic E2 evidence only.

## Boundaries and remaining work

- The historical Windows thumbnail first-attempt failure remains preserved; its root cause is **UNCONFIRMED**. The current exact source/test HEAD passed the Windows Python 3.10 and 3.13 thumbnail checks. Do not widen timeouts, skip assertions, or change production behavior without a reproducible failure and instrumentation.
- No filesystem multi-file compare-and-swap, lock, or atomic snapshot is claimed.
- No real dictionary scan, real PDIC/PPP/SECTION/Profile/OCR save/reopen, performance benchmark, or accuracy claim.
- Windows R3 E3, #483 W1–W11, #503 human Undo/Redo, and human operator acceptance: **NOT PERFORMED / DEFERRED**.
- R6 real-label learning and R8 real scans: **DEFERRED**.

Next: continue a read-only audit of the remaining SECTION/crop-to-save source-witness handoff, and add another RED-first test only if a concrete stale-owner or source-drift counterexample is found.
