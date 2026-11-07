# Round 140 — retain publication-error identity across confirmed OCRed/PDIC conflicts

## Baseline

Same Issue #562 / Draft PR #663 / `refactor/562-retire-root-image-utils-20261024`.
The preceding Round 139 HEAD `3b5aee6c7747b10ebffb59dbfe876e46cddce910` already preserves the original low-level read exception at four post-export, pre-PDIC ownership checkpoints. Round 140 covers a separate gap: the **original exporter or PDIC writer** exception could be lost as structured data when a later, affirmative sidecar conflict made compensation unsafe.

## Production changes

Owner: `src/picture_capture/ocr/batch_publication.py`.

Five confirmed/uncertain conflict exits now expose `RuntimeError.publication_error` as the **identical** original caught exception, not merely an interpolated `repr`:

1. OCRed exporter raises and PDIC bytes have changed.
2. OCRed exporter raises and observed OCRed bytes are not the expected exported bytes (foreign proofreading).
3. OCRed exporter raises and the PDIC read just before attempted compensation fails. This path also exposes `verification_error` and uses it as the explicit exception cause.
4. OCRed exporter raises and PDIC changes between failed-export inspection and attempted compensation.
5. PDIC writer raises but PDIC bytes have changed, so the commit may have occurred.

Other conflict paths from earlier rounds already retain their structured error objects. Existing exception *types*, Chinese messages, explicit causes, optimistic snapshot checks, and fail-closed disk behavior remain unchanged. None of these five changes retries, replaces or deletes a disk file.

## Tests and verification

`tests/test_issue562_publication_conflict_error_identity_round140_20261027.py` provides **five** fault-injection scenarios, checking object identity, error cause, old or concurrent manual bytes, single/no PDIC writer invocation and absence of rollback staging artifacts.

As always, check exact final HEAD six-platform CI and three-platform OCR Platform Smoke. No queued/in-progress/failed/cancelled job may be called passed.

## Unresolved boundary

Optimistic version reads cannot supply an atomic cross-process compare-and-swap or crash-safe OCRed/PDIC transaction. The last observation may race a non-cooperating writer. Manual real-scanned dictionary pages, GUI review, source image pixel coordinates, PPP/SECTION/PDIC roundtrip and crop/export parity remain **OPEN / NOT PASSED**; tests do not replace that acceptance gate.

PR #663 remains **Draft / Open / Unmerged**; never mark Ready or merge without the manual acceptance gate.
