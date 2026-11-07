# Round 146 — R3 marker recheck after final OCRed/PDIC observations

## Scope and owner

Issue #562, Draft PR #663, branch
`refactor/562-retire-root-image-utils-20261024`.

Production owner: `src/picture_capture/ocr/batch_publication.py`,
`publish_existing_pdic_ocr`. The batch exporter publishes OCRed first and
then PDIC; R3 proofreading uses a per-PDIC `.<PDIC>.r3-inflight.json`
recovery marker. A clean batch completion must not be reported while an
unresolved R3 transaction has taken ownership of the page.

## Previously uncovered window

Earlier rounds checked R3 at entry, before OCRed export, before PDIC writer
dispatch, in failure compensation, and immediately after the successful PDIC
writer. **After** that last check, the batch path still reads OCRed, may
perform a third expensive SECTION/source-image validator, and then reads
OCRed and PDIC again. An R3 transaction could stage its recovery marker
during these post-commit reads or the final validator; all sidecar bytes
could still match the expected values, so the batch function returned
normally despite a pending R3 recovery journal.

## Fix

After the final OCRed/PDIC observations, unconditionally invoke the
existing `_reject_unresolved_r3_marker(pdic_path)`. It uses `lstat` and
refuses any present marker, including a directory or dangling symlink;
unreadable status also fails closed. This runs for both validator-equipped
and legacy no-validator callers, without changing the existing exporter,
writer, validator order, PDIC/PPP/SECTION formats, OCRed bytes, source pixel
coordinates, or Windows spawn/Tk paths.

Both OCRed and PDIC have already been committed when this last check
runs. A late marker produces a visible error **without unilateral
rollback**, preserving both disk versions for R3 recovery / manual
reconciliation. No journal is created or removed by this check.

## Regression

`tests/test_issue562_r3_postcommit_final_marker_round146_20261028.py`
contains nine parametrized real-filesystem cases:

- R3 marker appears during the post-writer OCRed read (with/without
  provenance validator), third SECTION/source validation, final OCRed
  read, or final PDIC read: refuse clean success, retain both committed
  sidecars and the marker;
- the final marker `lstat` becomes unreadable after PDIC publication
  (with/without validator): propagate failure and retain both files;
- normal no-marker completion (with/without validator): preserve exact
  legacy exporter/writer/validator order and byte content.

## Remaining safety and release gates

This is a **last observation**, not an interprocess CAS or lock. A
noncooperating R3 writer can still stage a marker after this final check.
There is no crash/power-loss-atomic OCRed+PDIC transaction or durable
cross-process recovery protocol. The real scanned dictionary-page manual
acceptance (ordinary/OCR/combined detection, original image pixel
coordinates, Profile/Tk, PDIC/PPP/SECTION save/reopen and crop/export)
remains **OPEN / NOT PASSED**. Cross-platform six-combination CI, three
OS OCR smoke, architecture guard and security checks must be verified on
the **final exact HEAD**; queued jobs are not passes. Keep PR #663
**Draft / Open / Unmerged**, never merge or mark Ready automatically.
