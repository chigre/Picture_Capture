# PC-CQ v1.3.0 G1 — stale original-word / foreign PDIC publication guard (2026-10-29)

## Source-level race
The filtered writer already used exact original-image page/X/Y but read
`original_word` without enforcing it when the coordinate matched a
single record. A foreign review or main-canvas save could have updated
that same coordinate since the filter snapshot; the old writer would
replace the newer word with stale human input.

The writer also caught any exception from publication or post-write
verification and unconditionally wrote its pre-save `original_entries`
back to disk. If another writer had published different PDIC bytes,
that "rollback" overwrote the foreign change. An atomic single-file
replace does **not** establish version ownership for a rollback.

## Tests and bounded fix
Fail-first tests-only commit `7d64cf5991caf6c0d8dfd7724a2ad3c3702ad8a3`,
`tests/test_g1_focused_pdic_foreign_word_and_rollback_20261029.py`.
Six tests exercise real PDIC parsing/writing and controlled concurrent
mutations: unique-XY stale word; same-page conflict blocking other
pending rows; unchanged source success; source changed during image
read; ambiguous writer exception with a foreign publication; and
post-write verification failure with a foreign publication.

`proofreading/focused_pdic_updates.py` now:
- Verifies the selected coordinate's disk `word` still equals the
  snapshot's original headword, including the unique-XY case.
- Compares exact observed PDIC source bytes after parsing and just
  before publication; refuses a changed file without any write.
- Leaves a failed/ambiguous post-publication file untouched. It does
  **not** make a second blind `_write_pdic_atomic` call on exception.
  Failed callbacks retain user edits for controlled review/retry.

The writer still rejects duplicate ambiguous XY and mixed conflicts
per entire page, preserves PDIC format and validates post-write
readback. The app-facing signature and current injection seams remain
unchanged. These checks are optimistic guards, **not OS-level
multi-process CAS or power-loss atomicity**.

## Gate/exclusions
Verify exact final HEAD Windows/macOS/Ubuntu Python 3.10/3.13 CI,
OCR Smoke 3/3 and CodeQL Python+Actions 2/2. Human native Windows
dictionary acceptance E3, FocusOut/IME, 20 Undo/Redo, PDIC/PPP/SECTION
save/reopen, pixel-level crop parity, and #483 W1–W11 remain
NOT PERFORMED. PR #663 must remain Draft/Open/Unmerged, main unchanged,
#503/#562/#483 open.
