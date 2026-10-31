# Round 137 — OCRed ownership after post-rollback PDIC check (2026-10-27)

## Baseline and owner

- Previous exact HEAD: `5d94794d3297d8da5f192cef7cedb9bf17237265`.
- Six-platform CI: [#40510333308](https://github.com/chigre/Picture_Capture/actions/runs/40510333308), completed success (Windows/macOS/Ubuntu, Python 3.10/3.13, 6/6); OCR Platform Smoke: [#40510333665](https://github.com/chigre/Picture_Capture/actions/runs/40510333665), completed success (3/3).
- Owner: `src/picture_capture/ocr/batch_publication.py:_restore_ocred_if_unchanged`, used by failed OCRed export, failed SECTION validation, and failed PDIC save recovery.

## Failure and change

Round 136 protected the *pre-mutation* PDIC callback: an editor could change OCRed while that callback ran, and the compensating replace/unlink would otherwise destroy the edit. Round 131 additionally checked PDIC ownership **after** successful OCRed compensation. However, the post-rollback PDIC callback can itself be slow or invoke filesystem hooks. An editor can publish new OCRed bytes during that callback, after the rollback's own successful disk-state verification. Previously, the helper could then return without noticing the newer OCRed version, letting the caller report only its original publication failure and implying a restored old pair.

After a successful post-rollback PDIC check, the helper now re-reads OCRed and compares its observed bytes (including absence for newly created sidecars) with the pre-export snapshot. If OCRed differs, it reports an indeterminate pair and **never** attempts another compensation. If OCRed cannot be read, it exposes the exact `verification_error` and explicit exception cause without performing further writes. This is an additional observation, not an atomic ownership guarantee. The existing post-rollback PDIC conflict error retains precedence when that callback itself fails.

`tests/test_issue562_ocred_post_rollback_pdic_race_round137_20261027.py` contains eight scenarios: replace/delete with an OCRed edit in the second PDIC callback; replace/delete with the final OCRed read denied; replace/delete through the complete failed-PDIC-save path with a proofreader edit during the fifth PDIC read; and both unchanged normal-error paths. The tests assert the preserved foreign bytes, PDIC bytes, error object identity, exception chain, single PDIC save attempt and no temporary artifacts.

## Remaining risks and acceptance

This is still optimistic version checking, **not** cross-process atomic compare-and-swap. A non-cooperating writer can modify OCRed after the final read. OCRed/PDIC are not a single atomic transaction; process termination, power loss, and recovery of unknown in-flight commits remain unresolved.

PR #663 must remain **Draft / Open / Unmerged**. Representative real dictionary scan, proofreading, PPP/SECTION/PDIC save and reopen manual acceptance remains **OPEN / NOT PASSED**. Synthetic fault-injection tests cannot close that gate.

The initial full CI run [#40518192846](https://github.com/chigre/Picture_Capture/actions/runs/40518192846) exposed two failures in the new integration test on macOS and Windows: the fault was injected on PDIC read #6, but the actual post-rollback callback is read #5 (initial, after export, after failed save, pre-mutation, post-rollback). Corrected the test and its read-count assertions without changing production logic. Recheck the corrected exact HEAD before declaring this round green.
