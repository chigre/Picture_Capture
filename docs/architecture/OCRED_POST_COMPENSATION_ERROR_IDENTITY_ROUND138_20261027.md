# Round 138 — preserve post-compensation PDIC verification error identity (2026-10-27)

## Scope

Issue #562, Draft PR #663, `src/picture_capture/ocr/batch_publication.py`.
On baseline `e6c342b0c802f94c30e9d26f51b388306fec8d0b`, the six-platform CI and three-platform OCR Platform Smoke had completed successfully after the Round 137 regression test read-count correction.

## Recovery diagnostic contract

`_restore_ocred_if_unchanged` performs a final PDIC ownership callback **after** an OCRed sidecar replacement or deletion has succeeded. If this callback raises, the program must not perform another OCRed or PDIC write: the pair's state is uncertain. The outer publication caller retains its original `publication_error` plus its `rollback_error`, and the rollback exception retains the failing PDIC verification error as its `__cause__`.

Round 138 additionally assigns the exact exception object to `rollback_error.verification_error`, aligning this recovery path with other indeterminate OCRed/PDIC reads. When the PDIC ownership callback wraps an underlying filesystem failure, the recovery chain deliberately preserves both levels: `rollback_error.__cause__ is rollback_error.verification_error`, and `rollback_error.verification_error.__cause__` is the original I/O exception; callers must not assume these two exception objects are identical. This is an exception-diagnostic improvement only: no file format, transaction order, coordinates, public signature, Windows worker semantics or Tk behavior changes.

Four parametrized fault-injection scenarios in `tests/test_issue562_ocred_post_rollback_error_identity_round138_20261027.py` cover:
- existing versus newly created OCRed sidecars;
- direct post-compensation PDIC callback failure and full failed-PDIC-save propagation;
- `publication_error`, `rollback_error`, `verification_error` and explicit cause object identity;
- exact original bytes/absence, no second PDIC writer call and no stray temporary files.

## Acceptance / limits

Optimistic snapshot checks do **not** provide cross-process atomic compare-and-swap or two-file durable transactions. Non-cooperating writers, hard termination, power loss and later external writes still require reconciliation.

PR #663 remains **Draft / Open / Unmerged**. Representative real dictionary-page GUI scans, manual proofreading, OCR/ordinary/combined behavior, PPP/SECTION/PDIC save/reopen and crop/export parity are **OPEN / NOT PASSED**. Synthetic tests cannot satisfy manual acceptance.

Final exact-head six-platform CI and OCR Platform Smoke must both be verified separately; no pending run may be declared passed.
