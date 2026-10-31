# G3 R4.2 — read-only crop launch acknowledgement and Tk worker-start ownership

Date 2026-11-01 Asia/Singapore. Synthetic E2 only. Same Draft PR #663; no root modules, PDIC/PPP/SECTION/Profile formats, OCR models or persistent settings changed.

## Baseline and source graph

Actual GitHub baseline: main `ec20989ea8c026cca5337293e67850b6b6df30f2`, only Draft/Open/Unmerged PR #663, no unresolved review threads, #503/#562/#483 OPEN. Prior exact-head `f9d2f807193a5c0d5919339feb4e9622eb562520`: [CI #41238054379](https://github.com/chigre/Picture_Capture/actions/runs/41238054379) 6/6 + Risk gate SUCCESS; [OCR #41238054368](https://github.com/chigre/Picture_Capture/actions/runs/41238054368) 3/3 SUCCESS; [CodeQL #41238051230](https://github.com/chigre/Picture_Capture/actions/runs/41238051230) Python/Actions 2/2 SUCCESS.

The GUI crop read-only dispatch call path is `focused_filter_workflow.py` -> `_schedule_filter_next_batch_preload` or `_request_filter_batch_render` -> `parent._start_ui_worker` -> `ui/background_job_runtime.py::start_ui_worker` -> `Thread.start()` -> queue -> Tk poll callback. The real scheduler returns `-1` during UI shutdown without registering a worker. Old crop callers did catch -1 and throw on launch, but a synchronous compatibility adapter could deliver `done/failed` *before* returning -1 or raising. This could cache an unacknowledged crop, repaint human editors, or start a direct retry reentrantly. Separately, a thread constructor/start exception left the scheduler's new handler/active/close-wait reservations and displaced older same-key callback handlers.

## Real failure-first tests

- `d83e05d833cc281be778c84fb5d6f00f1e3cde36`, [CI #41240906808](https://github.com/chigre/Picture_Capture/actions/runs/41240906808): **macOS Python3.13 8 targeted FAILED / 5,242 passed / 2 skipped**. Eight cases: crop mode prefetch/direct × early done/failed × handoff -1/raises. First failure in each case violates strict no-publish-before-ack. Two separate synchronous-return success controls were also added. This red commit is **not accepted as a gate**.
- `465943db85e84aab1c3e0ea406511645949133b6`, [CI #41241036808](https://github.com/chigre/Picture_Capture/actions/runs/41241036808): **macOS Python3.10 16 targeted FAILED / 5,246 passed / 2 skipped**: eight preceding crop cases plus eight scheduler cases (constructor/start × prior same-key active worker yes/no × wait-on-close yes/no). Previously unstarted workers leaked registrations and erased prior handlers. Success and shutdown refusal controls tested separately. Red commit **not a passed gate**.

## Bounded production changes

1. `abc0f34316b23199c705663ec4c786c58c0d6fcf`: new pure launch helper in `src/picture_capture/ui/readonly_worker_launch.py`, shared only by the prefetch and direct crop dispatch points in `focused_filter_workflow.py`. The first inline done/failed is buffered until normal scheduler return; a thrown exception or -1 rejects it and invokes the existing generic, source/epoch/save guarded caller failure exactly once. An accepted terminal is single-shot, and normal legacy `None` return remains accepted. No second cache or source authority introduced.
2. `116cc02dcbbbc336624926f97d99e1921fcef9f3`: only `ui/background_job_runtime.py::start_ui_worker` thread creation/start exception boundary changed. Before replacement, save prior same-key generation and handler references; on failing Thread constructor/start remove new handler, active and wait-on-close token, restore older handlers and generation, then re-raise to the existing caller's generic refusal handling. Successful startup retains the original replacement and poll behavior. No new daemon/thread lifecycle or global hook.

## Independent gates and exclusions

At doc authoring, **final code+docs exact-HEAD six Windows/macOS/Ubuntu × Python3.10/3.13, Risk-tier/gate, OCR 3 OS, CodeQL Python and Actions remain PENDING**, must be checked on the actual latest SHA. Do not infer completion from previous SHA, red CI, or source-only run. Keep PR #663 Draft/unmerged, main unchanged; no force push, issue closure, skipping/weakening gates.

Residual outside this fix: if Tk `after()` scheduling itself raises **after** a real thread was started, no claim of atomic cancellation or final durable-write reconciliation is made. Human/real-scanned dictionary validation and Windows E3 do not follow from synthetic E2. PDIC/PPP/SECTION/Profile schema, manual-selection, source XY/identity, OCR algorithms, and experiment-default OFF states unchanged.

**NOT PERFORMED:** Windows R3 E3 operator; #483 W1–W11; #503 manual compound Undo/Redo; real ordinary/OCR/combined dictionary scan, PDIC/PPP/SECTION/Profile reopen/crop/export and representative measured benchmarks. **DEFERRED:** R6 real labels and R8 real scans. No private files uploaded.
