# G3/R3 focused save: dispatch uncertainty, human edits, and stale callback isolation

**Date:** 2026-10-31. **Scope:** Synthetic E2 guards for the focused ReviewWindow save/close workflow only. Sole development PR [#663](https://github.com/chigre/Picture_Capture/pull/663) remains Draft/Open/Unmerged. Baseline `main@ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged.

## Verified test-first findings

The initial test-only commit `d928e65c02f01f79a549175e55ec2b08fbba1cda` introduced eight targeted parametrized tests in `tests/test_g3_r4_focused_dispatch_fail_closed_20261031.py`. Before fixes, [CI #41187323339](https://github.com/chigre/Picture_Capture/actions/runs/41187323339) directly showed **8 failures** in both Ubuntu Python 3.13 (**5,046 passed / 3 skipped**) and macOS Python 3.13 (**5,047 passed / 2 skipped**). Failure classes:

1. Synchronous `_start_ui_worker` exceptions escaped with synthetic private path text and discarded the pending original correction; both former close-intent values failed.
2. A newer same-X/Y edit and an explicit in-flight user reversion needed distinct recovery semantics after ambiguous scheduling.
3. A two-page snapshot was lost or not fully restored when the initial dispatch failed.
4. Iterating an unreadable `project.images` source raised after the pending edits had already been cleared.
5. Closing when no worker launched (project missing, or a silent no-op) incorrectly promised to close after a nonexistent save.

Those failures were observed before the source correction; this intentionally red SHA is not an accepted CI gate. Further test-only `81803283befd455664ed42e1ec6d33e40aa29528` added a late-callback/uncertain-dispatch negative control plus a positive explicit retry. Test-only `cc4177e43505e4821bfc1154ee0f2a34e14a98f0` separately covers late `done` and `failed` callbacks arriving **after** a second accepted retry. Do not claim their pre-fix red test evidence unless the corresponding CI actually reports those assertions.

## Corrective changes and guarantees

- `8e965bec9e273446dac5c10cf21b11b77ab6cd8e`: in `src/picture_capture/ui/focused_filter_workflow.py`, construct page-list snapshot before clearing in-memory pending human edits. Catch synchronous scheduler failure, restore each unconfirmed snapshot edit without overwriting newer edits or human reversions, disarm close intent, show only generic status/dialog and flag the launch as unconfirmed. A late callback **while the launch remains unconfirmed** cannot certify publication, reconcile Entry words, or auto-trigger a retry.
- `505510937db43bef5382b3de39b5e78d76a55fc3`: `src/picture_capture/ui/review_close_actions.py` distinguishes actual running worker from idle pending changes and a failed launch. In all latter cases it refuses auto-close, regardless of an empty pending queue after a human reversion. No unstarted work is labeled "saving".
- `9f746b98467c85be0cc5dc8d6139b551a72e2e1c`: add monotonic **in-memory dispatch serial** to the worker callbacks. A late callback from an older, rejected scheduler attempt cannot alter `_filter_save_running`, pending edits, close intent, Tk status or another accepted retry's state. This is callback ownership, **not** a cross-process lock or a disk transaction.
- `446072815202434fd895bd35ac4f5df6018f8d8d`: extend the native real-Tk `scripts/gui_g3_focused_controls_smoke.py` synthetic fixture: actual ReviewWindow StringVar human correction → injected synchronous `_start_ui_worker` failure → visible editor and pending crop witness retained, no PDIC byte mutation, generic Tk error, no window close → explicit subsequent close with actual worker and PDIC 8-field source XY validation. This is disposable synthetic GUI E2 and not a human E3 acceptance.

If dispatch failed after partially handing work off, its disk effect remains **uncertain**. No automatic rollback or retry is permitted on that evidence; the PDIC original-word guard and source image/SECTION witness must still validate before any later explicit write. No OS-level cross-file CAS or atomic multiple-page write is claimed.

## Persistent and privacy boundaries

This batch changes no PDIC/PPP/SECTION/manual_selection/Project Profile/OCR schema or saved file format, no source X/Y or historical model/pickle identities, no OCR cache ownership, no new root shim or architecture baseline relaxation, and no default-OFF experimental flag. No real project paths, words or scans are uploaded. Exceptions may include real private paths, so the UI displays only static generic messages.

## Verification and stop rules

Exact final documentation HEAD **must** pass independently: CI Windows/macOS/Ubuntu × Python 3.10/3.13 **6/6** plus Risk-tier and its CI gate; OCR Platform Smoke Windows/macOS/Ubuntu **3/3**; CodeQL Python and Actions **2/2**. Separate conditional documentation architecture job **SKIPPED** is neither a pass nor a failure of its assertions; standard CI architecture guards remain mandatory. Check Draft/Open/Unmerged, main unchanged and zero unresolved review threads before closing E2.

**Not performed:** Windows real-device R3 E3, [#483](https://github.com/chigre/Picture_Capture/issues/483) W1–W11, [#503](https://github.com/chigre/Picture_Capture/issues/503) complex Undo/Redo, real dictionary scans and PDIC/PPP/SECTION save/reopen, original-image large-file perf, R6 human labels or R8 scan acceptance. No merge/Ready or issue closure.
