# G3 R4.2 / R3 — synchronous focused-close save-trigger failure (2026-10-31)

## Live starting point and scope

- Sole open code PR: [#663](https://github.com/chigre/Picture_Capture/pull/663), Draft, unmerged. Baseline `main@ec20989ea8c026cca5337293e67850b6b6df30f2`; do not merge/mark Ready.
- Previous exact HEAD `f1d436be11655c087cb30c95b805fe3c6a14dd57` was verified: [CI #41185135896](https://github.com/chigre/Picture_Capture/actions/runs/41185135896) six OS/Python 6/6 + Risk tier + Risk-tier CI gate SUCCESS; independent Documentation architecture job SKIPPED; [OCR #41185135720](https://github.com/chigre/Picture_Capture/actions/runs/41185135720) three OS 3/3 SUCCESS; [CodeQL/PR #41185132099](https://github.com/chigre/Picture_Capture/actions/runs/41185132099) Python/Actions 2/2 SUCCESS. No unresolved PR review threads.
- New boundary: while the *ordinary* review `review.save()` exception was already sanitized, the focused rows branch of `ui.review_close_actions.close_review` directly invoked `_flush_focused_changes_now()` outside the exception guard. A synchronous I/O/scheduling error could leave the close callback with an uncaught exception containing a local source path or a private candidate word. This is separate from background worker `failed` callbacks.

## Test-first reproduction and bounded correction

- **Test-only commit** `f6626b6b22def93ef50a584a5a1555dc1fe37b90` adds `tests/test_g3_r4_review_close_sync_flush_failure_20261031.py`. Its two parametrizations inject a synthetic exception with a fake private-looking path into the synchronous focused-save trigger, with both absent and preexisting close intent. The test requires: the ReviewWindow never finishes closing; no stale close intent; the exact pending human correction remains; one generic status and one generic Tk dialog; no private exception text or traceback in visible/output channels. It does not claim an already-scheduled writer can be rolled back or that bytes were committed.
- **Production commit** `8761355fa957f82990612007c0988a2bc5ca0a82` catches this *focused* synchronous failure at the review-close coordinator and fails closed with a generic status/modal and `_filter_close_after_save=False`; it neither discards pending changes nor declares the attempted write successful. Ordinary close and existing asynchronous focused completion/refusal paths remain unchanged.
- Red-first CI: [#41186527418](https://github.com/chigre/Picture_Capture/actions/runs/41186527418) **pending at documentation authoring**. This test predates the production fix; only the actual CI/test results can establish a observed red.
- Fix/source exact-head CI, three-OS OCR and CodeQL: **not yet verified at documentation authoring**. Verify on final documentation HEAD, not by transferring prior SHA's passing evidence.

## Contract and limitations

No root module, feature defaults, original X/Y, PDF/image bytes, PDIC/PPP/SECTION/manual_selection/Profile/OCR schema, R3 cross-file recovery, baseline architecture guard or human project data changed. The new handler only governs synchronous GUI close-trigger failure. Do not claim global disk CAS or cross-page atomicity from this change.

Still **NOT PERFORMED**: Windows R3 E3 operator acceptance, #483 W1–W11, #503 complex Undo/Redo, real dictionary page scan/GUI source XY save/reopen, original image latency, R6 human labels and R8 real-scan acceptance. Automated synthetic E2 remains distinct from human E3. The one PR stays Draft/Open/Unmerged.
