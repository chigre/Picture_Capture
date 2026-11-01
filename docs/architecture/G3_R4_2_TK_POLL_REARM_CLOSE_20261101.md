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
