# Round 143 — R3 recovery quarantine at the batch OCRed / PDIC publication boundary

## Scope and the previous integrity gap

Issue #562, Draft PR #663, existing-marker batch OCR publisher
`src/picture_capture/ocr/batch_publication.py`.

A proofreading R3 multi-file transaction writes
`.<PDIC filename>.r3-inflight.json` before modifying its owned PDIC and
related sidecars. Its canonical owner is
`proofreading/transactions.py:_recovery_path`. The regular PDIC writer
`io/formats.py:write_pdic` already refuses a new write while that marker
exists. However the batch OCR publisher previously exported OCRed **before**
dispatching its PDIC writer. On R3 conflict it might change OCRed first, then
discover the marker only when the PDIC writer rejected publication.

## Change and safety contract

The batch OCR publisher now detects a pending R3 marker by `lstat` of the
corresponding PDIC pathname (the same name as the existing writer guard).
`lstat` treats a directory or a symbolic-link marker as occupied rather than
following a potentially dangling link. All non-absence status/read errors
abort publication before any disk mutation.

The guard runs:

1. **Before any OCRed export** — a stale or unresolved R3 transaction blocks
   the entire new batch publication.
2. **After a failed exporter** — when R3 appears during export and the exporter
   raises, the publisher must not unilaterally undo OCRed because R3 may
   already own PDIC. Report the original `publication_error` and the
   marker-check `verification_error`, preserving object identities.
3. **Immediately before PDIC writer dispatch** — an R3 marker that appears
   during a successful OCRed export or expensive page-context validation
   blocks even custom legacy writers that bypass the shared `write_pdic`
   marker guard. Preserve observed OCRed bytes for explicit recovery, never
   guess at the other transaction's state.

This is a fail-closed ownership guard and **not a lock** or cross-process
atomic compare-and-swap. The R3 marker can appear between any final check and
filesystem mutation. No new marker is created by batch OCR, no preexisting
marker is automatically removed, and no transaction is automatically
recovered. The ordinary no-marker publisher call order and original image
coordinates are unchanged.

## Regression and acceptance

`tests/test_issue562_r3_ocr_publication_quarantine_round143_20261028.py`
covers fourteen parameterized cases: existing missing/present OCRed with
file/directory R3 marker; R3 appearing in successful or failing exporters;
R3 appearing in the final SECTION/source-image validator; normal no-marker
compatibility; and denied marker status reads both before export and inside
a failed-export handler. Assertions inspect actual sidecar bytes, prohibited
writer callbacks, exception identities and absent temporary files.

Check exact-head Windows/macOS/Ubuntu CI for current and Python 3.10 plus
three-platform OCR Smoke before concluding. A successful synthetic regression
is not a real dictionary-page acceptance test.

The real dictionary-page scan, manual proofreading, OCR/ordinary/combined,
PPP/SECTION/PDIC save/reopen, original-source-pixel coordinates and
crop/export parity acceptance remains **OPEN / NOT PASSED**.

Remaining risks: no globally cooperative locking of batch/R3 writers,
no cross-process CAS, no durable two-file OCRed/PDIC crash transaction,
and races after the final marker or byte observation.

Keep PR #663 **Draft / Open / Unmerged**; do not mark Ready or merge.

## Round 144 — R3 appearing inside the PDIC writer or compensation

The earlier pre-writer check cannot detect a recovery marker staged *inside*
the PDIC writer callback. If that callback subsequently raises without changing
PDIC bytes, the previous compensation logic would incorrectly consider OCRed
safe to restore. The publisher now checks the R3 marker immediately after a
failed PDIC writer **before** reading PDIC for a rollback decision, and after
a normally returning writer **before** reporting a clean commit. In the
failure case it preserves both the exact writer `publication_error` and
marker `verification_error`; no unilateral OCRed rollback is attempted.

All three PDIC-ownership verification callbacks used before compensating
OCRed (failed exporter, failed SECTION/source-image validation, failed PDIC
writer) now check the marker again. This also covers R3 starting while a
rollback temporary file is being staged/fsynced. Any conflict aborts
compensation and preserves the pending R3 marker for explicit review.

`tests/test_issue562_r3_pdic_writer_race_round144_20261028.py`
injects six real-filesystem cases: writer raises after staging R3, writer
returns after staging R3, and R3 appears only during the rollback ownership
callback, each with previously absent and existing OCRed. The tests assert
unchanged ownership, exact exception identities, no unintended compensating
write, and no leaked rollback temporary files.

These checks remain optimistic: a non-cooperating writer can create/remove a
marker after a check, and the two sidecars are not committed atomically.
Manual real-dictionary acceptance remains **OPEN / NOT PASSED**; PR #663 must
remain Draft, Open and Unmerged.


## CI compatibility fix: stable R3 error identifier

The first exact-head Round 144 Ubuntu CI found a historical Round 80
regression expecting the R3 refusal to contain the stable diagnostic
identifier `Unresolved R3 transaction`. The new guard's Chinese-only
message preserved behavior but broke this existing contract. Keep that
English identifier as the leading prefix **and** retain the descriptive
Chinese recovery instructions. The Round 143 pre-existing-marker test now
asserts both the stable identifier and the expected refusal; no R3 lock,
marker removal, write, rollback or acceptance requirement changed.
