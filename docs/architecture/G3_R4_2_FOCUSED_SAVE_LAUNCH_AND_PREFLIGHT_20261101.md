# G3 R4.2 — Ambiguous focused-save launch, explicit retry and preflight uncertainty (2026-11-01)

**Ownership:** `ui/focused_filter_workflow.py::_flush_focused_changes` owns the transient per-page pending human edits and per-dispatch uncertainty; `ui/review_close_actions.py::close_review` owns fail-closed window destruction. Existing PDIC writers and source witnesses are unchanged. This is synthetic E2 only, not a real operator acceptance.

## Failure boundary and failing-first evidence

An injected scheduler can execute the page worker, potentially publishing multiple PDIC pages, then raise before acknowledging launch. Previously the ReviewWindow retained human edits and set `_filter_save_launch_failed`, but did not mark batch pages `UNCERTAIN`. A later timer could dispatch another write. Closing the window invoked a "save now" before checking launch failure, creating a second implicit replay path.

- Test-first `642b437f84bcec8cf338265484c9e8c9ebb9857e`; [CI #41308310346](https://github.com/chigre/Picture_Capture/actions/runs/41308310346) produced targeted macOS Python 3.13 RED: 1 failed, 5,302 passed, 2 skipped. The expected batch page set `{0,1}` was empty.
- Close-triggered counterexample `9b7fbbc84737150bc8a8b93272afbdbe26af9c40`; [CI #41308530086](https://github.com/chigre/Picture_Capture/actions/runs/41308530086) Ubuntu Python 3.13 RED on the same missing uncertainty guard.
- Code `36c024e0bedbe2531f536cfc03e7130b4ae5edc5` preserves the full batch uncertainty on scheduler rejection; timers and close requests cannot retry it. The existing explicit retry path still launches after the operator verifies PDIC. A native Tk smoke [CI #41308743285](https://github.com/chigre/Picture_Capture/actions/runs/41308743285) exposed an obsolete expectation that a repeated close click should trigger another attempt; this was a real gate failure, not ignored.
- Native Tk integration correction `24e78710589a5f2f4cd347300b200146bc386987` changes the synthetic interaction sequence: close must be refused, explicit save must execute, stable file/UI outcomes must be observed, then close may succeed. Disk byte, pending human edit, traceback/path redaction, and no-double-callback assertions stay enforced. [CI #41309027670](https://github.com/chigre/Picture_Capture/actions/runs/41309027670) 6/6 + Risk-tier/gate SUCCESS; [OCR #41309027659](https://github.com/chigre/Picture_Capture/actions/runs/41309027659) 3/3; [CodeQL #41309024720](https://github.com/chigre/Picture_Capture/actions/runs/41309024720) Python/Actions 2/2 SUCCESS.

## Additional preflight-failure ownership test and correction

A later explicit retry can fail all-page source preflight **before this retry's writer**. The absence of a writer in the *new attempt* does not prove an older ambiguous dispatch never published PDIC. Before correction, this path reset the uncertain set and marked every page `not_committed`, allowing timer retry and falsely strengthening the disk claim.

- Additional RED test `b80d97534056137d9a4cef8322e97aaa772f200a`; [CI #41309554723](https://github.com/chigre/Picture_Capture/actions/runs/41309554723) Ubuntu Python 3.13: 1 targeted failure, 5,301 passed, 3 skipped.
- Minimal fix `023432f6f8f0a742743eb5b33c68379c38cf1d4c`: retain prior uncertain pages on preflight failure and label their latest `_filter_save_page_outcomes` as `uncertain`, not `not_committed`; unrelated never-attempted pages retain their safe prior classification.
- Exact source HEAD: [CI #41309765324](https://github.com/chigre/Picture_Capture/actions/runs/41309765324) 6/6 + Risk-tier/gate SUCCESS; [OCR #41309765320](https://github.com/chigre/Picture_Capture/actions/runs/41309765320) 3/3 SUCCESS; [CodeQL #41309762501](https://github.com/chigre/Picture_Capture/actions/runs/41309762501) Python/Actions 2/2 SUCCESS. Documentation architecture check SKIPPED.

## Contract and residual risk

This protects transient UI ownership under injected synthetic errors. It does **not** make a multi-file PDIC save atomic, implement durable compare-and-swap, rewrite schema, transform original image coordinates, or certify any real file/operator behavior. Automatic timer retry and implicit close retry remain blocked until uncertainty is resolved by an explicit operation; caller must inspect PDIC before that operation. Native GUI smoke is synthetic E2, **not** human acceptance.

**NOT PERFORMED:** Windows R3 E3, #483 W1–W11, #503 manual Undo/Redo, real dictionary scanning, real PDIC/PPP/SECTION/Profile/OCR save-reopen or human sign-off. **DEFERRED:** R6 real learning and R8 real scans. No benchmark accuracy/speed assertion. PR #663 remains Draft/Open/Unmerged; main unchanged.

This documentation/test checkpoint changes no production logic. Its own exact-head CI/OCR/CodeQL must be rechecked; historical source-head green gates do not substitute for the docs/test HEAD.
