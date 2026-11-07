# G3 R4.2 — focused human save ProjectState owner across launch, worker and Tk result

**Date:** 2026-11-03 (Asia/Taipei). **Sole PR:** #663, Draft/Open/Unmerged. **Baseline main:** `ec20989ea8c026cca5337293e67850b6b6df30f2`. **Source evidence:** `71e49785dc12bdff5b096b1a4e67f0604fd9a81e`; integrated HEAD `5d8765124149515402a537316c553453d830bd97`.

## Failure proven first

The existing scan and crop implementation pinned a ProjectState owner, but `_flush_focused_changes` originally read the then-current `self.parent.project` at save time and launched against its pages without verifying object identity with the scanned ProjectState. A replacement project with identical `root`, `images`, image bytes and SECTION witnesses was still a different edit owner. An old save could launch, its worker could run after a session replacement, and a successful completion could reconcile the replacement UI. This does **not** claim that ordinary project selection bypassed the existing guard preventing project switching while a ReviewWindow is alive.

[`3c3ceb40`](https://github.com/chigre/Picture_Capture/commit/3c3ceb4075f168efcf032bfd31f1e1f1ee430407) adds `tests/test_g3_r4_focused_save_project_session_owner_20261103.py`: three asynchronous/replacement cases (before launch, after dispatch/before preflight, after worker publication/before done) and a valid owner positive control. Disposable 8×8 BMP/PDIC and injected writer; no private/real user sources. [RED CI #41639594396](https://github.com/chigre/Picture_Capture/actions/runs/41639594396) six OS/Python matrix jobs **FAILURE** solely on three intended new assertions/job; Windows3.10 3 failed/5530 passed/2 skipped. Risk-tier CI gate **FAILURE**, not a pass.

## Correction and verified evidence

[`71e49785`](https://github.com/chigre/Picture_Capture/commit/71e49785dc12bdff5b096b1a4e67f0604fd9a81e) modifies only `src/picture_capture/ui/focused_filter_workflow.py` (+62/-0). A local read-only `save_session_is_current()` binds the save to the exact scanned ProjectState object, current scan serial, root and page list, and non-invalidated epoch, while preserving the legacy standalone-helper ABI. Refuses before clearing pending edits/launch, again in worker preflight and immediately before each page writer call. A successful old worker whose callback arrives after project replacement does **not** reconcile foreign entries or close, but preserves edits, labels pages `uncertain` and requires explicit inspection/retry.

[CI #41640032284](https://github.com/chigre/Picture_Capture/actions/runs/41640032284) 6/6 matrix **SUCCESS**, Risk tier and gate **SUCCESS**; [OCR #41640032317](https://github.com/chigre/Picture_Capture/actions/runs/41640032317) 3/3 **SUCCESS**; CodeQL Python/Actions 2/2 **SUCCESS**. Documentation architecture check **SKIPPED, not PASS**.

**Limits:** Checking the active ProjectState immediately before writer calls does not create OS-level transactional atomicity across different files or stop all external modification races. The simulated writer does not establish real PDIC/OCR quality. Human Windows R3 E3 and real scans/save-reopen not performed. No automatic replay of ambiguous save or rollback of third-party bytes.
