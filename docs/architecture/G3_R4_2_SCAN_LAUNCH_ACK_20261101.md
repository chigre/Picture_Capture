# G3 R4.2 — acknowledged scan launches before Tk terminal publication

Date: 2026-11-01 (Asia/Singapore). Sole Draft PR #663. Only disposable synthetic E2, not human Windows E3 or real dictionary scanning.

## Live verified baseline and real RED

GitHub main: `ec20989ea8c026cca5337293e67850b6b6df30f2`; only PR #663 Draft/Open/Unmerged, blocker Issues #503/#562/#483 Open, no review threads. Green baseline `2599eddb1360b0ae72c0a51c11961020008fbc49` had exact-head [six matrix CI #41223273971](https://github.com/chigre/Picture_Capture/actions/runs/41223273971) success (including Risk tier gate), [OCR #41223274149](https://github.com/chigre/Picture_Capture/actions/runs/41223274149) 3/3 success, [CodeQL #41223270845](https://github.com/chigre/Picture_Capture/actions/runs/41223270845) Python/Actions 2/2 success.

The preceding first/remainder scan one-shot callback guard did not distinguish **scheduler handoff acceptance** from early synchronous callback delivery. A worker dispatcher may invoke done/failed inline and **then throw** to report rejected or indeterminate launch. Previously the result was published before the exception and private exception details could escape; in a remainder scan this could double-publish incomplete page targets or poison completed status. A later callback from the rejected scheduler also lacked an acknowledgement gate.

Test-only commit `bcaee25f61b4b998ee251a9b4b106d013cd5b5a7` added four deterministic two-page synthetic counterexamples: initial scan (early done or failed then launch throws) and remainder scan (early done or failed then launch throws). [CI #41225930839](https://github.com/chigre/Picture_Capture/actions/runs/41225930839) **actually observed macOS Python3.13 4 targeted FAILED / 5,220 passed / 2 skipped**. All four raised `PRIVATE_LAUNCH_UNACKNOWLEDGED` before satisfying fail-closed assertions. This red-only SHA is not a passed gate.

## Minimal correction and expanded controls

`1790fe84c5196dcdbe40fdcb5c709b4886344203` modifies only `src/picture_capture/ui/focused_filter_workflow.py`: local helper `dispatch_scan_after_ack` wraps first and remainder scan scheduler calls. Its launch-state machine buffers the earliest terminal callback while `_start_ui_worker` has not returned. Only an acknowledged normal return dispatches the buffered result to the existing scan-epoch, active-mode and one-shot terminal guards. If the scheduler raises, buffered results are discarded, all late callbacks from that rejected launch are ignored, and the existing generic first/remainder failure handler marks the scan incomplete without leaking private exception paths. An already visible *first* batch remains available on remainder launch refusal; initial refused scan never publishes a batch. These workers read scanned metadata and do not write PDIC.

Extended synthetic controls `a83fc88fa848af394ef67f83f67d4e2e14fbb998` add no-callback launch refusal for both dispatch positions and two positive cases for **acknowledged inline completion** of initial/remainder scans. Tests assert no private error leakage, no duplicate status/UI changes after a rejected launch, continued publication when handoff is accepted, and preserved preexisting batches.

No changes to PDIC/PPP/SECTION/Profile or manual selection storage formats, source image XY, OCR algorithm, writer, actual data or default-OFF settings. No atomic filesystem CAS or speed/accuracy claims.

## Acceptance boundary

At creation of this document, final code+docs exact-head CI six Windows/macOS/Ubuntu×Python3.10/3.13 combos plus Risk tier/gate, OCR three-platform Smoke and CodeQL Python/Actions **PENDING**, not inherited from the previous green SHA or any intermediate commit. Verify independently and record terminal results in a PR #663 comment without an extra unchecked commit.

**NOT PERFORMED:** Windows R3 E3; #483 W1–W11; #503 real human compound Undo/Redo; real dictionary OCR, crop, PDIC/PPP/SECTION/Profile save-reopen; large-image benchmark, real-page source XY comparison.
**DEFERRED:** R6 genuine human verified-label learning, R8 real scans. No private content uploaded. Keep only PR #663 Draft/Open/Unmerged, main unchanged, Issues #503/#562/#483 Open.

Next review: SECTION boundary / scan source mutation on asynchronous read, rejected prefetch/direct crop worker launches, saved-page ownership under concurrent close. Only test-first on a separate reproducible failure and never bypass queued/failed gates.
