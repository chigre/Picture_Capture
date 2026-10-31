# Round 136 — OCRed rollback ownership after PDIC callback (2026-10-27)

## Baseline and owner

- Prior exact HEAD: `02601176671c5f77fa70ff2abf83e9681863b53c`.
- Six-platform CI: [#40501752490](https://github.com/chigre/Picture_Capture/actions/runs/40501752490), completed SUCCESS (Windows/macOS/Ubuntu, Python 3.10/3.13, 6/6); OCR Platform Smoke: [#40501752441](https://github.com/chigre/Picture_Capture/actions/runs/40501752441), completed SUCCESS (3/3).
- Owner: `src/picture_capture/ocr/batch_publication.py:_restore_ocred_bytes`; invoked through `_restore_ocred_if_unchanged` in the existing-PDIC batch OCR publication path.

## Failure and change

The compensating OCRed writer checked the expected OCRed bytes, then called a patchable `verify_before_mutation` callback to confirm PDIC ownership immediately before `os.replace` or `Path.unlink`. That callback can itself run slow or patched filesystem operations. A second editor could publish new OCRed bytes **during** PDIC verification; the old code would then replace or delete the newer human correction despite having checked OCRed just before the callback.

Both rollback branches now re-read OCRed **after** the PDIC callback returns and **before** destructive mutation, refusing compensation if the bytes no longer match `expected_current`. Read-denial likewise stops the rollback. The staged rollback temp file is cleaned up on the replace branch. Existing exception propagation preserves the original PDIC save failure and the rollback failure.

`tests/test_issue562_ocred_post_pdic_check_race_round136_20261027.py` covers six cases: replace/unlink when the PDIC callback edits OCRed, replace/unlink when the post-callback OCRed read is denied, and both paths through an actual failed-PDIC-save publication callback that edits OCRed during the final PDIC read. It asserts the preserved foreign bytes, original PDIC bytes, error chain, no unilateral rollback and no temporary artifacts.

## Limits and acceptance

This is a narrower optimistic ownership check, **not** a cross-process atomic compare-and-swap. External writes after the final read, two-file commit atomicity, process crashes and power loss remain unresolved. PR #663 must stay **Draft / Open / Unmerged**. Representative real dictionary scan, proofreading, PDIC/PPP/SECTION save and reopen acceptance remains **OPEN / NOT PASSED**; synthetic tests cannot satisfy that gate.

Check the newly committed exact-head six-platform CI and OCR Platform Smoke independently before declaring Round 136 green.
