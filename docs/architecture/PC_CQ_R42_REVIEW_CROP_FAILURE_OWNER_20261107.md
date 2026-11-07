# PC-CQ R4.2 — ReviewWindow crop failure owner and launch-retry safeguard (2026-11-07)

## Live branch and bounded source gap

At verification, main `ec20989ea8c026cca5337293e67850b6b6df30f2`, sole PR #663 Open/Draft/Unmerged on `refactor/562-retire-root-image-utils-20261024`. Source HEAD `683b624d32ff6a59808d596354fa457e6d9549e6`. No unresolved PR review threads were returned.

The canonical app `ui/background_job_runtime.py` already protects **superseded same-key worker generations**, including error callbacks. This work does **not** claim that previously covered case is vulnerable. Instead `ui/review_workspace_workflow.py::_request_render_rows`'s ordinary ReviewWindow `failed()` previously checked only window existence/closure. If page/geometry changed **before replacement worker dispatch**, it could publish an old crop error over the current page. In addition, a synchronous `_start_ui_worker` Thread.start/poll-registration exception escaped without a visible retry surface. Neither issue requires real files or changes persisted word ownership.

## Failure-first, synthetic E2

Test-only `dfc7d3362ba5b72cffede917e369d03b8e61306f`, [CI #42350346410](https://github.com/chigre/PictureCapture/actions/runs/42350346410): Ubuntu Python3.13 **4 FAILED / 5,766 passed / 3 skipped**; all six OS × Python matrix jobs FAILURE on the intentionally added negative tests (Risk-tier CI gate FAILURE is expected and NOT acceptance). The four checks establish stale page failure, stale geometry failure, RuntimeError launch failure and OSError launch failure. Positive controls for current worker failure and normal successful launch PASS. The synthetic `/synthetic/review-crop-failure/page.png` is a path sentinel only, not a user's image.

Test file: `tests/test_r42_review_crop_failure_owner_20261107.py`. No guard/assertion was weakened or xfailed.

## Minimal production fix and safeguards

Source `683b624d32ff6a59808d596354fa457e6d9549e6` changes only `src/picture_capture/ui/review_workspace_workflow.py`. `failed()` now refuses status/label publication when captured project/page/index/settings/auto-zoom/viewport/manual-zoom inputs no longer match current ReviewWindow geometry. It catches expected stale-window access errors fail-closed. At dispatch, RuntimeError/OSError/Tk TclError from worker construction/start/poll registration is sent to the existing visible failure handler; existing human editor rows are not destroyed, and a subsequent explicit request can dispatch again.

This is a crop/error-state UI guarantee, **not** an OS-level atomic transaction, a guarantee of a completed crop, automatic infinite retry, or evidence of real-world text-save parity. Central generation handling remains unchanged. No PDIC/PPP/SECTION/Profile/OCR schema, persistence writer, raw source XY, original image, private sample, experiment-default OFF switch, or learned OCR policy was changed.

## Exact source-head GREEN and documentation checkpoint boundary

- [CI #42350577910](https://github.com/chigre/PictureCapture/actions/runs/42350577910): six Windows/macOS/Ubuntu × Python3.10/3.13 matrix **6/6 SUCCESS**, Risk tier and Risk-tier CI gate **SUCCESS**; Ubuntu3.13 **5,770 passed / 3 skipped**, compatibility runner, Linux GUI smoke, compile and wheel SUCCESS.
- [OCR #42350577904](https://github.com/chigre/PictureCapture/actions/runs/42350577904): Windows/macOS/Ubuntu **3/3 SUCCESS**.
- [CodeQL #42350575452](https://github.com/chigre/PictureCapture/actions/runs/42350575452): Analyze Python and Actions **2/2 SUCCESS**. The aggregate CodeQL neutral check does not replace the two completed analyses.
- Documentation architecture check **SKIPPED, NOT PASS**.
- This audit and state/resume checkpoint are a **subsequent docs HEAD** with their own checks; they cannot inherit these exact-source run results without independent re-check.

## Resume and exclusions

**Single next action:** Read LIVE main/#663 Open/Draft/Unmerged HEAD and review threads; FIRST verify THIS new documentation checkpoint exact-head Windows/macOS/Ubuntu × Python3.10/3.13 CI six matrices, Risk-tier + Risk-tier CI gate, OCR three OS, and CodeQL Python/Actions. Documentation architecture SKIPPED is NOT PASS. Fix failures from real job logs. Then run a NEW, independent synthetic RED-first R3 ordinary ReviewWindow/main save failure-retry/partial rebind case, or R4.2 SECTION/crop-save epoch case with a genuinely new counterexample. Existing background_job_runtime already suppresses superseded same-key terminal callbacks; do not re-fix that path. Keep #663 sole Draft; no merge, force, schema/XY/consent/private data changes. Manual Windows R3 E3, #483 W1-W11, #503 Undo/Redo, real dictionary scan and PDIC/PPP/SECTION/Profile/OCR save-reopen, R6 real-label and R8 real-scan remain NOT PERFORMED/DEFERRED.

Human Windows R3 E3; #483 W1–W11; #503 manual Undo/Redo; representative real scans and PDIC/PPP/SECTION/Profile/OCR save/reopen: **NOT PERFORMED / DEFERRED**. R6 human label learning and R8 live scans: **DEFERRED**. Keep #663 Draft and main unmodified.
