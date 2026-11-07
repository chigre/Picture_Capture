# G3 R4.2 — exact original-image source XY across crop batch signature and worker

**Date:** 2026-11-03 SGT. **Repository:** chigre/Picture_Capture. **Sole production PR:** #663, Draft/Open/Unmerged. **main:** `ec20989ea8c026cca5337293e67850b6b6df30f2`. **Source/test SHA:** `929d65d5beb0d32795bb5ac4cd3bd90e488f1dd0`.

## Root cause and scope

The focused human-edit queue has strict page/XY type validation, and the downstream PDIC writer refuses invalid source coordinates. But its upstream crop-cache owner still formed `_filter_batch_snapshot` signatures using `int(target["x"])` / `int(target["y"])` outside the source-failure guard. Thus a fractional or numeric-text target could alias a valid image/PDIC/SECTION crop-cache signature. The separately dispatchable off-thread `_prepare_filter_batch_payload` also used `int(target["page_index"])` for indexing and `int(target["x"])`, `int(target["y"])` for matching. A malformed target could display an unrelated PDIC word crop even though a subsequent save would be refused. This is a synthetic defensive failure, not a claim observed in real dictionary data.

## Fail-first and valid controls

[`dbda31eb`](https://github.com/chigre/Picture_Capture/commit/dbda31ebbd3f8bda4362ee09946c0de3c0ab5d23): new synthetic-only 8×8 BMP + eight-field PDIC test file. Six invalid XY cache-key cases; ten malformed/off-range target page/XY worker cases; one valid integer snapshot+worker geometry positive control. [RED CI #41631995853](https://github.com/chigre/Picture_Capture/actions/runs/41631995853): all six Windows/macOS/Ubuntu × Python3.10/3.13 jobs completed **FAILURE** with exactly sixteen intended new assertions in each. Ubuntu3.13 16 failed/5512 passed/3 skipped; Windows3.10 16 failed/5513 passed/2 skipped. Risk-tier CI gate FAILURE on RED remains recorded.

## Minimal correction, exact-head verified

[`929d65d5`](https://github.com/chigre/Picture_Capture/commit/929d65d5beb0d32795bb5ac4cd3bd90e488f1dd0) edits only `src/picture_capture/ui/focused_filter_workflow.py` (+26/-17), using existing strict integer `_source_page_index` and `_exact_page_coordinate`. Validate the cache signature and source witness inside the existing fail-closed `try`; the worker validates page bounds/identity and source XY before image cache access, then compares entries to verified values. No pixel cropping algorithm/zoom, PDIC writer, serialized format, worker launch, experimental default, or source-marker coordinate changes.

- [CI #41632643807](https://github.com/chigre/Picture_Capture/actions/runs/41632643807): all six OS/Python matrix jobs **SUCCESS**, Risk tier and gate **SUCCESS**; macOS Python3.13 5529 passed/2 skipped.
- [OCR #41632643864](https://github.com/chigre/Picture_Capture/actions/runs/41632643864): three platforms **SUCCESS**.
- [CodeQL #41632639670](https://github.com/chigre/Picture_Capture/actions/runs/41632639670): Python and Actions **SUCCESS**.
- Documentation architecture check **SKIPPED, not a PASS**. Final docs checkpoint must pass its own exact-head checks.

## Safety and acceptance boundaries

These checks prove synthetic E2 rejection of malformed source identities, not Windows R3 E3, actual operator selection, dictionary OCR/PDIC save-reopen, byte-level multi-file atomicity or performance improvement. No private dictionary/PDIC/PPP/SECTION/Profile/OCR data was used or uploaded. No rollback over foreign bytes or auto-resume from an uncertain write is claimed. Windows R3 E3, #483 W1–W11, #503 human Undo/Redo, and real dictionary scans/save-reopen are **NOT PERFORMED/DEFERRED**. R6 real-data learning and R8 real scans remain DEFERRED.

**Next independent audit:** asynchronous crop direct callback versus prefetch, same-key reissue and project/scan epoch identity, and SECTION readback at actual publication boundaries; require a fresh executable RED-first counterexample, not a speculative change. Keep main unchanged and only PR #663 Draft/Open/Unmerged.
