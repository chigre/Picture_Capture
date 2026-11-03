# G3 R4.2 — revalidate ready-prefix provenance when the streamed tail fails

**Date:** 2026-11-03, Asia/Taipei. **Repository:** chigre/Picture_Capture. **Sole PR:** #663 Draft/Open/Unmerged. **main:** `ec20989ea8c026cca5337293e67850b6b6df30f2`. **Verified source/test:** `6c6ab74ae7970ed7061b60dd52945d006a3f67f6`.

## Root cause

`run_focused_filter` streams complete batches while a read-only remainder worker scans later pages. Successful first and remainder callbacks already validate scan epoch source witnesses. However, `start_remaining_scan.remaining_failed` previously set `_filter_scan_failed` and retained prior ready batches without rechecking their PDIC/OCR/SECTION bytes or current ProjectState object. When a prior scanned page changed just before the later worker failed, an old preview could remain labeled as a valid partial result. This is a synthetic defensive hazard; the normal UI already prevents deliberate project switching with ReviewWindow alive and there is no real-source watcher.

## Executable fail-first evidence

[`779031b3`](https://github.com/chigre/Picture_Capture/commit/779031b3c003343e5cc616e01b3f06bd00a69452) changes only `tests/test_g3_r4_streaming_scan_failure_20261031.py`. The new parameterized test has four deterministic disposable source cases: earlier page's PDIC edit, new OCR cache, new SECTION file and a different ProjectState object referencing the exact same root/page list. It requires old epoch invalidation and generic source warning while keeping the pending human correction unchanged and redacting private error detail. The unchanged existing no-drift test proves a normal failed remainder retains the ready batch. [RED CI #41651036164](https://github.com/chigre/Picture_Capture/actions/runs/41651036164): six OS/Python matrix **FAILURE** on exactly four new assertions each (Windows3.10: 4 failed, 5539 passed, 2 skipped; Ubuntu3.13: 4 failed, 5538 passed, 3 skipped), RED Risk-tier CI gate FAILURE. No unrelated regression was counted as expected.

## Correction and source validation

[`6c6ab74a`](https://github.com/chigre/Picture_Capture/commit/6c6ab74ae7970ed7061b60dd52945d006a3f67f6) edits only `src/picture_capture/ui/focused_filter_workflow.py` (+7/-0). After the failed remainder terminal claims dispatch ownership, it reuses the already defined `verify_scan_epoch_sources(start_position)` to check only the previously completed prefix and session identity. A mismatch invalidates the epoch by the existing `_reject_active_filter_scan_epoch` path; a valid prefix keeps original partial-batch status and displayed edits. Checks run only after a tail failure, not on the normal fast scan.

[CI #41652027345](https://github.com/chigre/Picture_Capture/actions/runs/41652027345): **6/6 SUCCESS** Windows/macOS/Ubuntu × Python3.10/3.13, architecture guard SUCCESS, Risk-tier/gate SUCCESS. [OCR #41652027478](https://github.com/chigre/Picture_Capture/actions/runs/41652027478) three OS **3/3 SUCCESS**. [CodeQL #41652019610](https://github.com/chigre/Picture_Capture/actions/runs/41652019610) Python and Actions **2/2 SUCCESS**. Documentation architecture check SKIPPED, not PASS. The final documentation checkpoint requires its own exact-head verification.

## Boundaries

No real dictionary/medical data, actual OCR scans, operator interactions, real PDIC save/reopen or performance measurement. No writer, image/XY, PDIC/PPP/SECTION/Profile schema or experimental-default changes. The check detects byte drift at a terminal boundary but cannot atomically lock external writers or give cross-file CAS guarantees. Windows R3 E3, #483 W1–W11, #503 human Undo/Redo and real scan/save-reopen remain NOT PERFORMED/DEFERRED; R6 learning and R8 real scans DEFERRED.
