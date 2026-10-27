# Round 145 — R3 quarantine after slow source/SECTION checks, before OCRed export

## Risk and owner

Issue #562 / Draft PR #663, existing-marker batch OCR:
`src/picture_capture/ocr/batch_publication.py:publish_existing_pdic_ocr`.

Round 143–144 introduced an unresolved R3 recovery-marker guard at batch
entry, after failures, and just before PDIC writer dispatch and OCRed
compensation. However, the first optional `validate_page_context()`
call may hash a large scan or inspect SECTION files and be followed by slow
PDIC and OCRed snapshot reads. A concurrent R3 proofreading transaction can
stage its `.<PDIC>.r3-inflight.json` marker **after** the initial guard and
before batch OCRed export. Because the old code only rechecked prior PDIC/
OCRed bytes, it could still publish OCRed while R3 held a page transaction,
then discover R3 too late at the pre-PDIC writer checkpoint.

## Change

Inside the page-context validation branch, after the second PDIC and OCRed
ownership checks and immediately before exporting OCRed, invoke the existing
`_reject_unresolved_r3_marker(pdic_path)`. This checks the marker via
`lstat` (so an actual file, directory, or dangling symlink is occupied).
An existing marker, or an unreadable marker status, fails closed **before
any OCRed export or PDIC writer call**, retaining original sidecar bytes.

No additional R3 marker is written or cleaned up by the batch worker.
The no-validator compatibility path keeps its existing call order and R3
checks. The guard is an observation only: a noncooperative writer can still
race after the final check; this does not create a two-file transaction,
cross-process CAS, durable journal, or crash recovery.

## Regression tests

`tests/test_issue562_r3_post_context_preexport_round145_20261028.py`
adds eight parametrized cases:

- Marker staged by the initial provenance callback, or during the last
  pre-export OCRed read (both when OCRed previously exists and is absent);
- Marker-stat permission failure arising only after validation (two cases);
- Successful no-marker control cases (two) that preserve three validator
  calls, the OCRed-before-PDIC writer order and original disk bytes/geometry
  boundary.

The injected marker read race explicitly covers a previously absent OCRed
path whose second read raises `FileNotFoundError`: the pending R3 marker
still must block creation of a new sidecar.

## Acceptance and verification

Review latest *exact commit* Windows/macOS/Ubuntu tests for normal Python
and Python 3.10, Risk-tier gate and three-platform OCR Smoke independently.
Any queued or running job remains **NOT VERIFIED**.

The real scanned dictionary-page GUI OCR, ordinary and combined detection,
manual proofreading, original pixel coordinates, PDIC/PPP/SECTION save/
reopen and crop/export parity remain **OPEN / NOT PASSED**. Synthetic
regressions do not satisfy manual acceptance. Keep PR #663
**Draft / Open / Unmerged**, never merge or mark Ready automatically.
