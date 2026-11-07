# G3 R4.2 — declined prefetch and direct crop on worker scheduler close (-1)

Date 2026-11-01 (Asia/Singapore). Only synthetic automatic E2, not manual Windows E3 or real dictionary data.

## Independently verified baseline and concrete runtime contract

Live GitHub main `ec20989ea8c026cca5337293e67850b6b6df30f2`, sole Draft PR #663, #503/#562/#483 Open, review threads 0. Baseline `18be51852eeb39179219fd4ac72738a451b18846`: [CI #41226272640](https://github.com/chigre/Picture_Capture/actions/runs/41226272640) 6/6 plus Risk tier gate, [OCR #41226272559](https://github.com/chigre/Picture_Capture/actions/runs/41226272559) 3/3, [CodeQL #41226269712](https://github.com/chigre/Picture_Capture/actions/runs/41226269712) Python+Actions 2/2, all confirmed SUCCESS.

`src/picture_capture/ui/background_job_runtime.py::start_ui_worker` checks `self._ui_worker_shutdown or self._ui_close_requested` and **returns -1 without creating a task**. Successful normal launches return a positive generation ID; historical in-process test shims often return `None` and still deliver callbacks. Thus crop callers must specifically recognize `-1`, not reject every falsy or non-integer return.

The old `_schedule_filter_next_batch_preload` set `_filter_prefetch_key` before calling this scheduler, and ignored the returned `-1`, permanently occupying a key with no worker. The old direct `_request_filter_batch_render` replaced the visible crop UI with an asynchronous loading placeholder and ignored `-1`, leaving it waiting for a callback that never exists.

## Real RED-first and bounded fix

Test-only `f12778e0478bf68208ba54be1dd08c76e503506e` adds two deterministic synthetic regression tests for the concrete close sentinel. [CI #41227343838](https://github.com/chigre/Picture_Capture/actions/runs/41227343838) Ubuntu Python 3.13 **actually recorded 2 targeted FAILED / 5,227 passed / 3 skipped**. Both target cases fail on the expected stale prefetch key and indefinite direct loading message. Red-only commit is not a passed gate.

Production commit `d54dc5c895e00c5ff678ed0cea0219e2c12e3860` changes only `src/picture_capture/ui/focused_filter_workflow.py`: both crop launch call sites handle `generation == -1` and a raised launch exception, routing through their existing, once-only `failed(None,None)` callback. Existing owner scan epoch/cache key/render serial checks and human pending-edit/save safety gates determine if state may be mutated. A rejected prefetch releases its key and may recover the visible preview through the bounded existing failure path; a rejected direct render clears its loading placeholder to a generic failure message. No exception strings or private paths are shown in Tk messages.

Supplemental `03ebd57b41c6a1ca189df6cbe3122a38e8fcf970` adds two tests for scheduler exceptions occurring **before** any worker callback. Standard successfully launched worker control tests remain in the same suite.

## Scope and residual risks

This patch does not change or replace `_start_ui_worker` / worker-thread runtime, ownership generations, original image XY, actual PDIC writes, PDIC/PPP/SECTION/Profile/manual-selection persistent formats, OCR algorithms or default-OFF experiments. A hypothetical shim that calls done inline **and then raises** is not proven to be rollback-safe by this patch; actual `background_job_runtime.py` schedules UI callbacks through the Tk poll queue, not synchronously inside `start_ui_worker`. Do not claim a transactional file-level CAS. No measured improvements in speed or accuracy.

At document creation, final *code+tests+docs* HEAD CI Windows/macOS/Ubuntu × Python3.10/3.13 **6/6 + Risk tier/gate**, OCR Smoke **3/3**, CodeQL Python/Actions **2/2** are **PENDING**. Confirm exact SHA independently and record completed results in PR #663 without creating an extra unverified commit.

**NOT PERFORMED:** Windows R3 E3, #483 W1–W11, #503 operator/compound Undo/Redo, real dictionary PDIC/PPP/SECTION/Profile OCR/crop/save-reopen, real page/XY and large-image benchmark. Synthetic E2 is not human E3.
**DEFERRED:** R6 verified-label learning, R8 real scans. No private files uploaded, no Ready/merge/force push, main unchanged, blocker issues remain Open.

Next audit: worker generation race where a prefetch is explicitly cancelled and reissued under identical source before first terminal; SECTION source/ownership changes during concurrent save. Test-first only when uniquely reproducible. Preserve sole Draft PR.
