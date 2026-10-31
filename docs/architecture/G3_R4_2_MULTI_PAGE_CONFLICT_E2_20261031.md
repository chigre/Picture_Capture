# G3 R4.2 — two-page partial commit, PDIC conflict, and late writer failure (2026-10-31)

## What this synthetic E2 packet does and does not claim

The existing live focused-mode worker preflights **all edited pages' original image and SECTION source witnesses** before any PDIC write. This prevents a stale second page source from allowing an avoidable partial first-page write. But **a foreign PDIC word edit is distinct from image/SECTION drift**: the page-level writer checks exact source X/Y and the original word before publication. A different page can therefore commit successfully even if a later page has a *word conflict*, and an I/O failure can still occur after the all-page preflight.

Two additional **test-only** cases in `tests/test_g3_r4_focused_save_source_ownership_20261031.py` (source commit `f643404029a5428c2928781d56d430a8afd42a46`) cover those documented limits without changing the writer or inventing cross-page OS atomicity.

## Deterministic two-page checks

**Case A — page-2 original-word conflict:** Construct two completely disposable 8×8 synthetic BMP pages and their PDIC/SECTION files. Accept separate displayed source witnesses for each page. Queue `edit-one` and `edit-two`, then change only page 2's PDIC word to `external` (the PDIC is intentionally not part of the displayed save witness). Run the actual focused workflow worker and done callback. Require exactly one physical write for page 1, no overwrite of the foreign page 2, a single page-2 conflict warning, a page-2-only restored pending edit retaining its crop witness, and no page-1 requeue/duplicate write. On a **deliberate second manual retry** of the pending page-2 correction, require no new PDIC write and no modification to either committed page 1 or foreign page 2. The main Entry word must reflect the confirmed page-1 commit and retain its original XY.

**Case B — later page-2 exception after page-1 publication:** Both source witnesses and PDIC words are initially valid. The real page-1 writer commits, then a deliberately injected `OSError` interrupts the page-2 writer. The actual Tk failed callback cannot atomically classify page 1 as globally verified or silently discard page 2; it must **retain both edits as uncertain**, preserve the first published PDIC without rollback, leave page 2 unchanged, cancel close-on-save and give a **generic, path-free error**. Manual inspection must resolve the uncertain page-1 state; the application must not silently re-publish the first row over a foreign writer.

These tests use `SimpleNamespace`/deterministic callbacks, not a physical Windows operator, real private dictionary image or actual GUI keyboard. The late-error injection is a **synthetic controlled failure**, not an observed field incident.

## Validation boundary

At this document author's checkpoint, the source [CI #41178622263](https://github.com/chigre/Picture_Capture/actions/runs/41178622263), [OCR #41178622249](https://github.com/chigre/Picture_Capture/actions/runs/41178622249), and [PR CodeQL #41178619392](https://github.com/chigre/Picture_Capture/actions/runs/41178619392) were running. This docs change creates a **new HEAD** requiring an independent completed-success result for all 6 OS/Python CI jobs + Risk-tier gate, OCR3/3, CodeQL Python/Actions2/2, no unresolved review threads and untouched main. A conditionally skipped Documentation architecture job is not a pass. Do not claim a red-first production defect: this tranche adds a missing safety assertion, with **no production code change**, unless tests reveal a real failure.

**Not performed:** real Windows R3 E3, [#483](https://github.com/chigre/Picture_Capture/issues/483) W1–W11, [#503](https://github.com/chigre/Picture_Capture/issues/503) complex Undo/Redo, G3 real dictionary visible crop/source XY save-reopen, and large-image real-device latency; R6 verified human labels and R8 actual scans **DEFERRED**. [Draft #663](https://github.com/chigre/Picture_Capture/pull/663) remains Open/Unmerged; main is frozen and no private project assets are uploaded.
