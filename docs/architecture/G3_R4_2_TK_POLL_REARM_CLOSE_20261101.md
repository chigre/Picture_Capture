# G3 R4.2 — recurring Tk poll rearm and durable close scheduler fail-closed

Date: 2026-11-01. Synthetic E2 only; no real scans or operator validation.

## Live baseline and observed RED
main `ec20989ea8c026cca5337293e67850b6b6df30f2`; sole Draft/Open/Unmerged PR #663; #503/#562/#483 Open. Prior final head `fde5e2a76288ed3dcd223640180d31cadfd27448` had successful exact-head gates documented in its PR comment. This tranche addresses a different boundary: recurring `after()` failure after the first successful poll, deferred `after_idle(on_close)` failure, and a close request hiding a window before its first observer could be scheduled.

**Test-only RED**: `923aa0754844959365732332fd83ccdf231168c2`, [CI #41283123003](https://github.com/chigre/Picture_Capture/actions/runs/41283123003). macOS Python3.13 actually recorded **7 new failures / 5267 passed / 2 skipped**; Ubuntu Python3.13 also failed. The remaining matrix may still be running; never transfer these failures as successful acceptance.

## Corrective source chain
- `adf8ee22`: bounded `schedule_ui_worker_poll` tries timed Tk `after` then at most one `after_idle` fallback until a timed poll succeeds. If both fail, preserve active and durable close-wait tokens, avoid private error text in status, and restore a closing window to visible retryable state. A deferred close `after_idle` failure falls back to direct `on_close()` on the same Tk callback thread.
- `b50d1301`: main-window close preflights poll scheduling before invalidating callbacks, setting close intent or withdrawing. Repeated close with an existing close intent but missing poll may re-arm without re-invalidating.
- `58eee5f4`: inject the runtime scheduler into the historical app lifecycle delegate without introducing another root module.
- `a03a7a67`: initialize the one-shot fallback latch in the main-window initialization owner.

The tests cover timed poll recovery, bounded fallback, both schedulers refusing during close, deferred close failure, accepted idle fallback and repeated close rearm. These are deterministic synthetic scheduling cases, not actual Tcl teardown or real file durability guarantees. A failed callback scheduler can still require explicit user retry or application restart; no silent claim of a completed write.

## Acceptance gate and boundaries
The final code+tests+docs HEAD must independently pass six Windows/macOS/Ubuntu × Python 3.10/3.13 CI jobs, Risk tier and Risk-tier CI gate, OCR three-platform Smoke, and CodeQL Python/Actions 2/2. **PENDING at authoring**. A SKIPPED conditional documentation architecture check is not a passed assertion. Do not mark E2 verified until exact-head results complete.

No persistent PDIC/PPP/SECTION/Profile/manual-selection schema, source X/Y, actual OCR, scan pixels, image data or experimental defaults changed. No private project data uploaded. No measured speed/accuracy claim. main unchanged; PR #663 remains Draft/Open/Unmerged; no issue closure.

**NOT PERFORMED**: Windows R3 E3, #483 W1–W11, #503 human complex Undo/Redo, real dictionary OCR/PDIC/PPP/SECTION/Profile save/reopen, real XY and benchmark.
**DEFERRED**: R6 human-verified label learning and R8 real scans.

Next: exact-head gate verification and any failure repair; then audit SECTION/source epoch, crop prefetch and save consistency under asynchronous completion.

## Follow-up — preserve close intent and make explicit poll retry safe (2026-11-01)

**Corrected RED chain and mock hygiene**
- Test-only `923aa0754844959365732332fd83ccdf231168c2` added recurring-poll, idle-close and close-preflight cases. Initial failures exposed that the synthetic close fake also needed `_poll_ui_worker_queue`; this test-fixture omission was corrected in `11db385d6e73bfff63141b537af8611436cf5f33`, alongside the strict leaf-owner inventory update for the two new runtime functions.
- Corrected fixture RED `57be8123006bd444ceda207681ea3f5fc7029625`, [CI #41284080942](https://github.com/chigre/Picture_Capture/actions/runs/41284080942), produced five failures on Ubuntu/macOS Python3.13. They established the remaining product gaps: the poll-failure handler reset `_ui_close_requested` after handlers had already been invalidated; explicit close retry did not re-arm the one-shot idle fallback; a successful retry did not hide the window again; a failed retry did not expose a visible retry surface.
- Source fix `1f338a368726c0cfd3c188f4bef1a0dec95b09ec` keeps close intent authoritative and callback suppression intact, deiconifies without cancelling the close intent, resets the bounded fallback latch only on an explicit close retry, and hides the window only after poll registration is accepted. Repeated close never invalidates the same generation twice. The initial close path still preflights the observer before setting close intent or hiding.

**Source exact-head verification**
- [CI #41284201872](https://github.com/chigre/Picture_Capture/actions/runs/41284201872): Windows/macOS/Ubuntu × Python3.10/3.13 **6/6 SUCCESS**, Risk tier SUCCESS, Risk-tier CI gate SUCCESS. Python3.13: Ubuntu 5,276 passed/3 skipped; macOS 5,277/2; Windows 5,277/2. Python3.10: Ubuntu 5,276/3; macOS 5,277/2; Windows 5,277/2.
- macOS Python3.13 native GUI smoke first attempt failed once at the synthetic in-flight PDIC reversion check with a coordinate conflict warning. The exact same job/head was rerun as job `124783274918` and completed SUCCESS: 5,277 passed/2 skipped, All checks passed. This transient result is explicitly retained; no source change occurred between the failed attempt and the successful rerun.
- [OCR #41284201873](https://github.com/chigre/Picture_Capture/actions/runs/41284201873): **SUCCESS 3/3 OS**.
- [CodeQL #41284199187](https://github.com/chigre/Picture_Capture/actions/runs/41284199187): **SUCCESS**, Analyze (python)/Analyze (actions) **2/2**.
- Documentation architecture check was **SKIPPED** by its workflow conditional, not counted as a pass. The final docs checkpoint commit still requires its own exact-head rerun.

**Boundaries**
- A single one-shot `after_idle` fallback is allowed until a timed `after()` succeeds; no infinite idle-spin. If both schedulers remain unavailable, preserve close intent and durable worker ownership, show a retry surface, and require explicit retry. This is not a guarantee against permanent Tcl teardown or process termination.
- Synthetic E2 only. No actual PDIC/PPP/SECTION/Profile data, scan pixels, OCR, persistent schema, source XY, real file atomicity, cross-process CAS, or benchmark claims.
- **NOT PERFORMED:** Windows R3 E3, #483 W1–W11, #503 manual Undo/Redo, real dictionary scan, real PDIC/PPP/SECTION/Profile/OCR save/reopen. **DEFERRED:** R6 real-label learning and R8 real scans.
- Next: exact-head documentation checkpoint verification, then fail-first audit of async SECTION/source epoch and crop prefetch/save consistency. Keep #663 Draft/Open/Unmerged and main unchanged.

