# G3 R4.2 — focused human-save launch refused by closed Tk worker (-1)

Date: 2026-11-01 (Asia/Singapore). Synthetic E2 only; no real dictionary scan or Windows operator E3.

## Live baseline and owner

At test start, `main@ec20989ea8c026cca5337293e67850b6b6df30f2` and sole Draft/Open/Unmerged PR #663. Issues #503, #562 and #483 Open; no review threads. Baseline `8af813ad96ba87c5741e9d4081b3ed137bd4bf8e`: [CI #41228910802](https://github.com/chigre/Picture_Capture/actions/runs/41228910802) six Windows/macOS/Ubuntu × Python 3.10/3.13 plus Risk tier/gate SUCCESS; [OCR #41228910853](https://github.com/chigre/Picture_Capture/actions/runs/41228910853) three OS SUCCESS. CodeQL at this baseline was not independently verified.

Actual `src/picture_capture/ui/background_job_runtime.py::start_ui_worker` returns **-1** when `_ui_worker_shutdown` or `_ui_close_requested` is set; this creates **no worker and no callback**. Earlier scan, crop prefetch and direct render call sites were fixed to handle the sentinel. The human-edit persistence dispatch in `src/picture_capture/ui/focused_filter_workflow.py::_flush_focused_changes` still ignored `-1`, after popping its queued corrections and setting `_filter_save_running=True`. This can leave an imaginary in-flight save or falsely accept an early compatibility callback. `wait_on_close=True` alone does not override shutdown refusal.

## Real test-first failure and bounded source fix

Test-only [`36ad0b2e`](https://github.com/chigre/Picture_Capture/commit/36ad0b2e866a4d9ab7a7385ed89ca2ca363fc7d0) added 6 cases: prior close intent false/true × no callback/inline done/inline failed then `-1`. These assert the same pending correction identity, unchanged synthetic bytes and target original, false running/close intent, one generic refusal, no private-path disclosure, and rejection of late callbacks. [CI #41237742113](https://github.com/chigre/Picture_Capture/actions/runs/41237742113) Ubuntu Python 3.13 **actually recorded 6 targeted FAILED / 5,233 passed / 3 skipped**. All six new cases fail on the old `_filter_save_launch_failed is False`; this intentionally red test-only commit is **NOT** an accepted green gate.

Production [`5c772741`](https://github.com/chigre/Picture_Capture/commit/5c7727413997aa9e010c703844e915ef1f345c01) performs a narrowly scoped change to the save scheduler call: capture its generation, and on exactly `generation == -1`, enter the already existing launch-rejected branch. This marks `_filter_save_launch_failed`, disarms the close intention, requeues uncommitted changes without erasing newer human edits, and discards buffered/late unacknowledged completion. A normal scheduler return (including legacy synchronous test shims returning None) preserves the existing acknowledgement contract; raised launch exceptions continue to use the same guard. No raw exception or project path is displayed.

## Validation and limitations

At document creation, source and final code+docs **exact-HEAD** CI six OS/Python plus Risk tier/gate, OCR three-platform Smoke, and CodeQL Python/Actions are **PENDING**. Do not reuse a prior SHA or treat the red test CI as successful. Preserve the sole Draft PR #663; no auto-merge, Ready transition, main change, issue closure, or force push.

No change to `background_job_runtime.py`, durable PDIC/PPP/SECTION/Profile formats, OCR cache, page/XY ownership, experiment defaults, persisted undo journals, or actual writing logic. This fix does not certify whether a *partly started* ambiguous worker committed bytes: the generic refusal deliberately retains edits for human reconciliation and retry. No measured accuracy or performance improvement claimed.

**NOT PERFORMED:** Windows R3 E3, #483 W1–W11, #503 manual compound Undo/Redo, genuine scanned/photographed dictionary page OCR/ordinary/combined, Profile, PDIC/PPP reopen, crop/export or measured latency. **DEFERRED:** R6 label training and R8 real scans. No private files uploaded.
